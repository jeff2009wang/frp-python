#!/usr/bin/env python
import sys
import socket
import time
import threading
import struct
import selectors
import logging
from collections import deque

import lib.ConnTool as ConnTool

sel = selectors.DefaultSelector()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('frps')


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


class ProxyManager:
    def __init__(self):
        self.active_frps = {}
        self.lock = threading.Lock()

    def register_frpc(self, proxy_name, frpc_conn):
        with self.lock:
            self.active_frps[proxy_name] = {
                'frpc_conn': frpc_conn,
                'user_queue': deque(),
                'last_heartbeat': time.time()
            }
            logger.info(f'Registered frpc for proxy: {proxy_name}')

    def unregister_frpc(self, proxy_name):
        with self.lock:
            if proxy_name in self.active_frps:
                try:
                    self.active_frps[proxy_name]['frpc_conn'].close()
                except Exception:
                    pass
                del self.active_frps[proxy_name]
                logger.info(f'Unregistered frpc for proxy: {proxy_name}')

    def add_user_conn(self, proxy_name, user_conn):
        with self.lock:
            if proxy_name in self.active_frps:
                self.active_frps[proxy_name]['user_queue'].append(user_conn)
                return True
            return False

    def get_user_conn(self, proxy_name):
        with self.lock:
            if proxy_name in self.active_frps:
                if self.active_frps[proxy_name]['user_queue']:
                    return self.active_frps[proxy_name]['user_queue'].popleft()
            return None

    def update_heartbeat(self, proxy_name):
        with self.lock:
            if proxy_name in self.active_frps:
                self.active_frps[proxy_name]['last_heartbeat'] = time.time()

    def get_frpc_conn(self, proxy_name):
        with self.lock:
            if proxy_name in self.active_frps:
                return self.active_frps[proxy_name]['frpc_conn']
            return None

    def is_alive(self, proxy_name):
        with self.lock:
            if proxy_name in self.active_frps:
                return time.time() - self.active_frps[proxy_name]['last_heartbeat'] < 30
            return False


proxy_manager = ProxyManager()


class Frps(threading.Thread):
    def __init__(self, user_port, frps_port):
        threading.Thread.__init__(self)
        self.user_port = user_port
        self.frps_port = frps_port
        
        self.user_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.user_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.user_sock.bind(('0.0.0.0', self.user_port))
        self.user_sock.setblocking(False)
        self.user_sock.listen(200)
        sel.register(self.user_sock, selectors.EVENT_READ, self.accept_user_connection)
        
        self.frps_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.frps_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.frps_sock.bind(('0.0.0.0', self.frps_port))
        self.frps_sock.setblocking(False)
        self.frps_sock.listen(200)
        sel.register(self.frps_sock, selectors.EVENT_READ, self.accept_frpc_connection)
        
        threading.Thread(target=self.check_timeouts, daemon=True).start()

    def check_timeouts(self):
        while True:
            time.sleep(10)
            current_time = time.time()
            with proxy_manager.lock:
                dead_proxies = [
                    name for name, info in proxy_manager.active_frps.items()
                    if current_time - info['last_heartbeat'] > 30
                ]
                for name in dead_proxies:
                    logger.warning(f'Proxy {name} timed out, unregistering')
                    proxy_manager.unregister_frpc(name)

    def accept_user_connection(self, sock, mask):
        try:
            user_conn, addr = sock.accept()
            optimize_socket(user_conn)
            user_conn.setblocking(True)
            
            if proxy_manager.active_frps:
                proxy_name = list(proxy_manager.active_frps.keys())[0]
                if proxy_manager.add_user_conn(proxy_name, user_conn):
                    logger.info(f'Received user connection from {addr}, queued for {proxy_name}')
                    
                    frpc_conn = proxy_manager.get_frpc_conn(proxy_name)
                    if frpc_conn:
                        try:
                            frpc_conn.sendall(struct.pack('i', 2))
                        except Exception as e:
                            logger.error(f'Failed to send command to frpc: {e}')
                else:
                    logger.warning('No active frpc, closing user connection')
                    user_conn.close()
            else:
                logger.warning('No active frpc, closing user connection')
                user_conn.close()
        except Exception as e:
            logger.error(f'Error accepting user connection: {e}')

    def accept_frpc_connection(self, sock, mask):
        try:
            frpc_conn, addr = sock.accept()
            optimize_socket(frpc_conn)
            frpc_conn.setblocking(False)
            sel.register(frpc_conn, selectors.EVENT_READ, self.handle_frpc_data)
            logger.info(f'Accepted frpc connection from {addr}')
        except Exception as e:
            logger.error(f'Error accepting frpc connection: {e}')

    def handle_frpc_data(self, frpc_conn, mask):
        try:
            data = frpc_conn.recv(4)
            if not data:
                logger.info('frpc connection closed')
                sel.unregister(frpc_conn)
                frpc_conn.close()
                proxy_manager.unregister_frpc('default')
                return
            
            cmd = struct.unpack('i', data)[0]
            logger.debug(f'Received command: {cmd}')
            
            if cmd == 1:
                proxy_manager.register_frpc('default', frpc_conn)
                
            elif cmd == 2:
                sel.unregister(frpc_conn)
                frpc_conn.setblocking(True)
                
                user_conn = proxy_manager.get_user_conn('default')
                if user_conn:
                    logger.info('Connecting user and frpc')
                    ConnTool.join(user_conn, frpc_conn)
                else:
                    logger.warning('No user connection available')
                    frpc_conn.close()
                    
        except Exception as e:
            logger.error(f'Error handling frpc data: {e}')
            try:
                sel.unregister(frpc_conn)
            except Exception:
                pass
            frpc_conn.close()

    def run(self):
        logger.info(f'frps started - listening on 0.0.0.0:{self.user_port} (user) and 0.0.0.0:{self.frps_port} (frpc)')
        while True:
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


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: python frps.py <frps_port> <user_port>')
        print('Example: python frps.py 7000 8001')
        sys.exit(1)
    
    try:
        frps_port = int(sys.argv[1])
        user_port = int(sys.argv[2])
        Frps(user_port=user_port, frps_port=frps_port).start()
    except ValueError:
        print('Error: Ports must be integers')
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info('Shutting down...')
        sys.exit(0)
