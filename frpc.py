#!/usr/bin/env python
import sys
import socket
import time
import threading
import struct
import selectors
import logging

import lib.ConnTool as ConnTool

sel = selectors.DefaultSelector()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('frpc')


def optimize_socket(sock):
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except Exception:
        pass
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
    except Exception:
        pass


class ConnectionPool:
    def __init__(self, server_host, server_port, target_host, target_port, pool_size=5):
        self.server_host = server_host
        self.server_port = server_port
        self.target_host = target_host
        self.target_port = target_port
        self.pool_size = pool_size
        self.work_conn_pool = []
        self.lock = threading.Lock()
        self.running = True

    def create_connection_pair(self):
        try:
            work_conn = socket.create_connection((self.server_host, self.server_port), timeout=5)
            target_conn = socket.create_connection((self.target_host, self.target_port), timeout=5)
            
            optimize_socket(work_conn)
            optimize_socket(target_conn)
            
            ConnTool.join(target_conn, work_conn)
            return work_conn
        except Exception as e:
            logger.error(f'Failed to create connection pair: {e}')
            return None

    def maintain_pool(self):
        logger.info(f'Starting connection pool with size: {self.pool_size}')
        while self.running:
            with self.lock:
                current_size = len(self.work_conn_pool)
                needed = self.pool_size - current_size
                
                if needed > 0:
                    logger.debug(f'Pool has {current_size} connections, creating {needed} more')
                    for _ in range(needed):
                        work_conn = self.create_connection_pair()
                        if work_conn:
                            self.work_conn_pool.append(work_conn)
            
            time.sleep(1)

    def get_connection(self):
        with self.lock:
            if self.work_conn_pool:
                return self.work_conn_pool.pop()
            else:
                logger.debug('Pool empty, creating new connection')
                return self.create_connection_pair()

    def stop(self):
        self.running = False


class Frpc:
    def __init__(self, server_host, server_port, target_host, target_port, pool_size=5):
        self.server_host = server_host
        self.server_port = server_port
        self.target_host = target_host
        self.target_port = target_port
        self.server_fd = None
        self.running = True
        self.auto_reconnect = True
        
        self.connection_pool = ConnectionPool(
            server_host, server_port, target_host, target_port, pool_size
        )
        
        self.connect_to_server()
        
        threading.Thread(target=self.connection_pool.maintain_pool, daemon=True).start()
        threading.Thread(target=self.heartbeat, daemon=True).start()

    def connect_to_server(self):
        retry_count = 0
        max_retries = 10
        retry_delay = 2
        
        while retry_count < max_retries and self.running:
            try:
                self.server_fd = socket.create_connection(
                    (self.server_host, self.server_port), timeout=5
                )
                optimize_socket(self.server_fd)
                
                self.server_fd.sendall(struct.pack('i', 1))
                self.server_fd.setblocking(False)
                
                try:
                    sel.unregister(self.server_fd)
                except Exception:
                    pass
                sel.register(self.server_fd, selectors.EVENT_READ, self.handle_controller_data)
                
                logger.info(f'Connected to server {self.server_host}:{self.server_port}')
                return True
                
            except Exception as e:
                retry_count += 1
                logger.warning(f'Connection attempt {retry_count} failed: {e}')
                if retry_count < max_retries:
                    time.sleep(retry_delay)
        
        logger.error('Failed to connect to server after maximum retries')
        return False

    def heartbeat(self):
        while self.running:
            try:
                if self.server_fd is not None:
                    self.server_fd.sendall(struct.pack('i', 1))
            except Exception as e:
                logger.error(f'Heartbeat failed: {e}')
                if self.auto_reconnect:
                    logger.info('Attempting to reconnect...')
                    self.connect_to_server()
            time.sleep(5)

    def handle_controller_data(self, server_fd, mask):
        try:
            data = server_fd.recv(4)
            if not data:
                logger.info('Server connection closed')
                if self.auto_reconnect:
                    self.reconnect()
                return
            
            cmd = struct.unpack('i', data)[0]
            logger.debug(f'Received command: {cmd}')
            
            if cmd == 2:
                logger.info('Received connection request from server')
                
                work_conn = self.connection_pool.get_connection()
                if work_conn:
                    work_conn.sendall(struct.pack('i', 2))
                    logger.info('Established working connection')
                else:
                    logger.error('Failed to get connection from pool')
                    
        except Exception as e:
            logger.debug(f'Error handling controller data: {e}')

    def reconnect(self):
        try:
            if self.server_fd:
                sel.unregister(self.server_fd)
                self.server_fd.close()
        except Exception:
            pass
        
        self.server_fd = None
        logger.info('Reconnecting to server...')
        self.connect_to_server()

    def stop(self):
        self.running = False
        self.connection_pool.stop()
        if self.server_fd:
            try:
                sel.unregister(self.server_fd)
            except Exception:
                pass
            self.server_fd.close()

    def run(self):
        logger.info('frpc started')
        try:
            while self.running:
                try:
                    events = sel.select(timeout=1.0)
                    for key, mask in events:
                        callback = key.data
                        try:
                            callback(key.fileobj, mask)
                        except Exception as e:
                            logger.error(f'Error in callback: {e}')
                except Exception as e:
                    logger.error(f'Error in select loop: {e}')
        except KeyboardInterrupt:
            logger.info('Received interrupt, shutting down...')
        finally:
            self.stop()
