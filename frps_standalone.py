#!/usr/bin/env python
import sys
import socket
import time
import threading
import struct
import selectors
import logging
import os

sel = selectors.DefaultSelector()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('frps')


CMD_HEARTBEAT = 1
CMD_CONNECTION = 2
CMD_REGISTER_PORT = 3
CMD_UNREGISTER_PORT = 4
CMD_DATA_CONNECT = 5


def optimize_socket(sock):
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception as e:
        logger.debug(f'TCP_NODELAY failed: {e}')
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except Exception as e:
        logger.debug(f'SO_KEEPALIVE failed: {e}')
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception as e:
        logger.debug(f'SO_REUSEADDR failed: {e}')
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    except Exception as e:
        logger.debug(f'Buffer size setting failed: {e}')
    try:
        sock.setsockopt(socket.IPPROTO_TCP, TCP_KEEPIDLE, 30)
        sock.setsockopt(socket.IPPROTO_TCP, TCP_KEEPINTVL, 10)
        sock.setsockopt(socket.IPPROTO_TCP, TCP_KEEPCNT, 3)
    except Exception as e:
        logger.debug(f'TCP keepalive settings failed: {e}')
    try:
        if hasattr(socket, 'TCP_WINDOW_CLAMP'):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_WINDOW_CLAMP, 1024 * 1024)
    except Exception as e:
        logger.debug(f'TCP window clamp failed: {e}')


TCP_KEEPIDLE = 4
TCP_KEEPINTVL = 5
TCP_KEEPCNT = 6


PKT_BUFF_SIZE = 4 * 1024 * 1024


class TransferStats:
    def __init__(self, name):
        self.name = name
        self.bytes_sent = 0
        self.bytes_recv = 0
        self.start_time = time.time()
        self.last_report = time.time()
        self.lock = threading.Lock()

    def add_sent(self, count):
        with self.lock:
            self.bytes_sent += count

    def add_recv(self, count):
        with self.lock:
            self.bytes_recv += count

    def report(self):
        with self.lock:
            current_time = time.time()
            elapsed = current_time - self.last_report
            total_elapsed = current_time - self.start_time
            
            if elapsed >= 5:
                sent_speed = (self.bytes_sent / 1024 / 1024) / elapsed
                recv_speed = (self.bytes_recv / 1024 / 1024) / elapsed
                total_sent = self.bytes_sent / 1024 / 1024
                total_recv = self.bytes_recv / 1024 / 1024
                
                logger.info(f'{self.name} - Sent: {total_sent:.2f} MB ({sent_speed:.2f} MB/s), '
                          f'Recv: {total_recv:.2f} MB ({recv_speed:.2f} MB/s), '
                          f'Time: {total_elapsed:.1f}s')
                
                self.bytes_sent = 0
                self.bytes_recv = 0
                self.last_report = current_time


def tcp_mapping_worker(conn_receiver, conn_sender, stats, direction):
    optimize_socket(conn_receiver)
    optimize_socket(conn_sender)
    
    try:
        peer_recv = conn_receiver.getpeername()
        peer_send = conn_sender.getpeername()
        logger.info(f'Starting {direction} worker: {peer_recv} -> {peer_send}')
    except Exception as e:
        logger.debug(f'Could not get peer names: {e}')
    
    last_activity = time.time()
    last_recv_time = last_activity
    last_send_time = last_activity
    total_bytes = 0
    recv_bytes = 0
    send_bytes = 0
    
    try:
        while True:
            try:
                data = conn_receiver.recv(PKT_BUFF_SIZE)
                if not data:
                    logger.debug(f'{direction}: Connection closed by receiver (after {total_bytes / 1024 / 1024:.2f} MB)')
                    break
                
                data_len = len(data)
                total_bytes += data_len
                recv_bytes += data_len
                
                if direction == 'forward':
                    stats.add_sent(data_len)
                else:
                    stats.add_recv(data_len)
                
                last_recv_time = time.time()
                
                try:
                    conn_sender.sendall(data)
                    send_bytes += data_len
                    last_send_time = time.time()
                except ConnectionResetError as e:
                    logger.error(f'{direction}: Connection reset while sending ({data_len} bytes): {e}')
                    logger.error(f'{direction}: Connection state - recv: {recv_bytes/1024/1024:.2f} MB, '
                               f'send: {send_bytes/1024/1024:.2f} MB')
                    break
                except BrokenPipeError as e:
                    logger.error(f'{direction}: Broken pipe while sending ({data_len} bytes): {e}')
                    logger.error(f'{direction}: Connection state - recv: {recv_bytes/1024/1024:.2f} MB, '
                               f'send: {send_bytes/1024/1024:.2f} MB')
                    break
                except OSError as e:
                    logger.error(f'{direction}: OS error while sending ({data_len} bytes): '
                               f'{type(e).__name__}: {e}, errno: {e.errno if hasattr(e, "errno") else "unknown"}')
                    logger.error(f'{direction}: Connection state - recv: {recv_bytes/1024/1024:.2f} MB, '
                               f'send: {send_bytes/1024/1024:.2f} MB')
                    break
                except Exception as e:
                    logger.error(f'{direction}: Unexpected error while sending ({data_len} bytes): '
                               f'{type(e).__name__}: {e}')
                    logger.error(f'{direction}: Connection state - recv: {recv_bytes/1024/1024:.2f} MB, '
                               f'send: {send_bytes/1024/1024:.2f} MB')
                    break
                    
            except socket.timeout:
                logger.warning(f'{direction}: Socket timeout')
                break
            except ConnectionResetError as e:
                logger.error(f'{direction}: Connection reset while receiving: {e}')
                logger.error(f'{direction}: Connection state - recv: {recv_bytes/1024/1024:.2f} MB, '
                           f'send: {send_bytes/1024/1024:.2f} MB')
                break
            except BrokenPipeError as e:
                logger.error(f'{direction}: Broken pipe while receiving: {e}')
                logger.error(f'{direction}: Connection state - recv: {recv_bytes/1024/1024:.2f} MB, '
                           f'send: {send_bytes/1024/1024:.2f} MB')
                break
            except Exception as e:
                logger.error(f'{direction}: Receive error ({total_bytes} bytes transferred): '
                          f'{type(e).__name__}: {e}')
                logger.error(f'{direction}: Connection state - recv: {recv_bytes/1024/1024:.2f} MB, '
                           f'send: {send_bytes/1024/1024:.2f} MB')
                break
        
        elapsed = time.time() - last_activity
        logger.info(f'{direction}: Stopped after transferring {total_bytes / 1024 / 1024:.2f} MB '
                   f'(idle for {elapsed:.1f}s)')
        
    except Exception as e:
        logger.error(f'{direction}: Fatal error: {type(e).__name__}: {e}')
    finally:
        try:
            conn_receiver.close()
        except Exception as e:
            logger.debug(f'{direction}: Error closing receiver: {e}')
        try:
            conn_sender.close()
        except Exception as e:
            logger.debug(f'{direction}: Error closing sender: {e}')


def join(connA, connB):
    optimize_socket(connA)
    optimize_socket(connB)
    
    try:
        peer_a = connA.getpeername()
        peer_b = connB.getpeername()
        conn_id = f'{peer_a}<->{peer_b}'
    except Exception as e:
        conn_id = f'conn_{id(connA)}'
        logger.debug(f'Could not get peer names: {e}')
    
    stats = TransferStats(conn_id)
    
    t1 = threading.Thread(target=tcp_mapping_worker, args=(connA, connB, stats, 'forward'), daemon=True)
    t2 = threading.Thread(target=tcp_mapping_worker, args=(connB, connA, stats, 'reverse'), daemon=True)
    
    t1.start()
    t2.start()
    
    report_thread = threading.Thread(target=stats.report, daemon=True)
    report_thread.start()
    
    return t1, t2


class ProxyManager:
    def __init__(self):
        self.frpc_connections = {}
        self.port_listeners = {}
        self.user_queues = {}
        self.data_connections = {}
        self.lock = threading.Lock()

    def register_frpc(self, frpc_conn, addr):
        with self.lock:
            conn_id = id(frpc_conn)
            self.frpc_connections[conn_id] = {
                'conn': frpc_conn,
                'addr': addr,
                'last_heartbeat': time.time(),
                'ports': set()
            }
            logger.info(f'Registered FRPC connection {conn_id} from {addr}')
            return conn_id

    def unregister_frpc(self, conn_id):
        with self.lock:
            if conn_id in self.frpc_connections:
                frpc_info = self.frpc_connections[conn_id]
                for port in list(frpc_info['ports']):
                    self.unregister_port(port)
                
                try:
                    frpc_info['conn'].close()
                except Exception as e:
                    logger.debug(f'Error closing FRPC connection: {e}')
                del self.frpc_connections[conn_id]
                logger.info(f'Unregistered FRPC connection {conn_id}')

    def register_port(self, conn_id, port):
        with self.lock:
            if conn_id not in self.frpc_connections:
                logger.warning(f'FRPC connection {conn_id} not found')
                return False
            
            if port in self.port_listeners:
                logger.warning(f'Port {port} already registered')
                return False
            
            try:
                listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind(('0.0.0.0', port))
                listener.listen(100)
                listener.setblocking(False)
                
                self.port_listeners[port] = {
                    'listener': listener,
                    'conn_id': conn_id
                }
                self.user_queues[port] = []
                self.frpc_connections[conn_id]['ports'].add(port)
                
                sel.register(listener, selectors.EVENT_READ, 
                         lambda s, m, p=port: self.accept_user_connection(s, m, p))
                
                logger.info(f'Port {port} registered for FRPC {conn_id}')
                return True
                
            except Exception as e:
                logger.error(f'Failed to register port {port}: {type(e).__name__}: {e}')
                return False

    def unregister_port(self, port):
        with self.lock:
            if port not in self.port_listeners:
                return
            
            port_info = self.port_listeners[port]
            conn_id = port_info['conn_id']
            
            try:
                sel.unregister(port_info['listener'])
                port_info['listener'].close()
            except Exception as e:
                logger.debug(f'Error unregistering port {port}: {e}')
            
            for user_conn in self.user_queues.get(port, []):
                try:
                    user_conn.close()
                except Exception:
                    pass
            
            del self.port_listeners[port]
            if port in self.user_queues:
                del self.user_queues[port]
            
            if conn_id in self.frpc_connections:
                self.frpc_connections[conn_id]['ports'].discard(port)
            
            logger.info(f'Port {port} unregistered')

    def add_user_conn(self, port, user_conn):
        with self.lock:
            if port in self.user_queues:
                self.user_queues[port].append(user_conn)
                return True
            return False

    def get_user_conn(self, port):
        with self.lock:
            if port in self.user_queues and self.user_queues[port]:
                return self.user_queues[port].pop(0)
            return None

    def get_frpc_conn(self, port):
        with self.lock:
            if port in self.port_listeners:
                conn_id = self.port_listeners[port]['conn_id']
                if conn_id in self.frpc_connections:
                    return self.frpc_connections[conn_id]
            return None

    def update_heartbeat(self, conn_id):
        with self.lock:
            if conn_id in self.frpc_connections:
                self.frpc_connections[conn_id]['last_heartbeat'] = time.time()

    def check_timeouts(self):
        current_time = time.time()
        with self.lock:
            dead_conns = [
                conn_id for conn_id, info in self.frpc_connections.items()
                if current_time - info['last_heartbeat'] > 30
            ]
            for conn_id in dead_conns:
                logger.warning(f'FRPC connection {conn_id} timed out')
                self.unregister_frpc(conn_id)

    def accept_user_connection(self, sock, mask, port):
        try:
            user_conn, addr = sock.accept()
            optimize_socket(user_conn)
            user_conn.setblocking(True)
            
            logger.info(f'Received user connection from {addr} on port {port}')
            
            if self.add_user_conn(port, user_conn):
                frpc_info = self.get_frpc_conn(port)
                if frpc_info:
                    try:
                        frpc_info['conn'].sendall(struct.pack('!i', CMD_CONNECTION) + struct.pack('!i', port))
                        logger.debug(f'Sent connection request for port {port} to FRPC')
                    except Exception as e:
                        logger.error(f'Failed to send connection request: {type(e).__name__}: {e}')
                        user_conn.close()
                else:
                    logger.warning(f'No FRPC connection for port {port}')
                    user_conn.close()
            else:
                logger.warning(f'No FRPC connection for port {port}')
                user_conn.close()
        except Exception as e:
            logger.error(f'Error accepting user connection: {type(e).__name__}: {e}')


proxy_manager = ProxyManager()


class Frps(threading.Thread):
    def __init__(self, frps_port):
        threading.Thread.__init__(self)
        self.frps_port = frps_port
        self.data_port = frps_port + 1
        
        self.frps_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.frps_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.frps_sock.bind(('0.0.0.0', self.frps_port))
        self.frps_sock.setblocking(False)
        self.frps_sock.listen(200)
        sel.register(self.frps_sock, selectors.EVENT_READ, self.accept_frpc_connection)
        
        self.data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.data_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.data_sock.bind(('0.0.0.0', self.data_port))
        self.data_sock.setblocking(False)
        self.data_sock.listen(200)
        sel.register(self.data_sock, selectors.EVENT_READ, self.accept_data_connection)
        
        threading.Thread(target=self.check_timeouts_loop, daemon=True).start()

    def check_timeouts_loop(self):
        while True:
            time.sleep(10)
            proxy_manager.check_timeouts()

    def accept_frpc_connection(self, sock, mask):
        try:
            frpc_conn, addr = sock.accept()
            optimize_socket(frpc_conn)
            frpc_conn.setblocking(False)
            conn_id = proxy_manager.register_frpc(frpc_conn, addr)
            sel.register(frpc_conn, selectors.EVENT_READ, 
                     lambda c, m, cid=conn_id: self.handle_frpc_data(c, m, cid))
            logger.info(f'Accepted FRPC connection from {addr}')
        except Exception as e:
            logger.error(f'Error accepting FRPC connection: {type(e).__name__}: {e}')

    def accept_data_connection(self, sock, mask):
        try:
            data_conn, addr = sock.accept()
            optimize_socket(data_conn)
            
            try:
                data = data_conn.recv(8)
                if len(data) == 8:
                    cmd = struct.unpack('!i', data[:4])[0]
                    port = struct.unpack('!i', data[4:8])[0]
                    
                    if cmd == CMD_DATA_CONNECT:
                        logger.info(f'Data connection request from {addr} for port {port}')
                        user_conn = proxy_manager.get_user_conn(port)
                        if user_conn:
                            logger.info(f'Connecting user and FRPC for port {port}')
                            try:
                                peer_user = user_conn.getpeername()
                                peer_data = data_conn.getpeername()
                                logger.debug(f'Connection pairs: {peer_user} <-> {peer_data}')
                            except Exception:
                                pass
                            join(user_conn, data_conn)
                        else:
                            logger.warning(f'No user connection for port {port}')
                            data_conn.close()
                    else:
                        logger.warning(f'Invalid data connection command: {cmd}')
                        data_conn.close()
                else:
                    logger.warning(f'Invalid data connection handshake (got {len(data)} bytes)')
                    data_conn.close()
            except Exception as e:
                logger.error(f'Error in data connection handshake: {type(e).__name__}: {e}')
                data_conn.close()
        except Exception as e:
            logger.error(f'Error accepting data connection: {type(e).__name__}: {e}')

    def handle_frpc_data(self, frpc_conn, mask, conn_id):
        try:
            data = frpc_conn.recv(4)
            if not data:
                logger.info(f'FRPC connection {conn_id} closed')
                try:
                    sel.unregister(frpc_conn)
                except Exception:
                    pass
                proxy_manager.unregister_frpc(conn_id)
                return
            
            cmd = struct.unpack('!i', data)[0]
            logger.debug(f'Received command: {cmd} from FRPC {conn_id}')
            
            if cmd == CMD_HEARTBEAT:
                proxy_manager.update_heartbeat(conn_id)
                try:
                    frpc_conn.sendall(struct.pack('!i', CMD_HEARTBEAT))
                except Exception as e:
                    logger.error(f'Failed to send heartbeat response: {type(e).__name__}: {e}')
                
            elif cmd == CMD_REGISTER_PORT:
                port_data = frpc_conn.recv(4)
                if port_data:
                    port = struct.unpack('!i', port_data)[0]
                    if proxy_manager.register_port(conn_id, port):
                        frpc_conn.sendall(struct.pack('!i', CMD_REGISTER_PORT) + 
                                        struct.pack('!i', port))
                    else:
                        frpc_conn.sendall(struct.pack('!i', CMD_REGISTER_PORT) + 
                                        struct.pack('!i', 0))
                
            elif cmd == CMD_UNREGISTER_PORT:
                port_data = frpc_conn.recv(4)
                if port_data:
                    port = struct.unpack('!i', port_data)[0]
                    proxy_manager.unregister_port(port)
                    frpc_conn.sendall(struct.pack('!i', CMD_UNREGISTER_PORT) + 
                                    struct.pack('!i', port))
                
        except Exception as e:
            logger.error(f'Error handling FRPC data: {type(e).__name__}: {e}')
            try:
                sel.unregister(frpc_conn)
            except Exception:
                pass
            proxy_manager.unregister_frpc(conn_id)

    def run(self):
        logger.info(f'FRPS started - listening on 0.0.0.0:{self.frps_port} (control) and 0.0.0.0:{self.data_port} (data)')
        while True:
            try:
                events = sel.select(timeout=1.0)
                for key, mask in events:
                    callback = key.data
                    try:
                        callback(key.fileobj, mask)
                    except Exception as e:
                        logger.error(f'Error in callback: {type(e).__name__}: {e}')
            except Exception as e:
                logger.error(f'Error in select loop: {type(e).__name__}: {e}')


def main():
    if len(sys.argv) != 2:
        print('FRPS Server v2.4 - High Performance Reverse Proxy with Dynamic Port Mapping')
        print('')
        print('Usage: frps <frps_port>')
        print('')
        print('Arguments:')
        print('  frps_port    Port for FRPC clients to connect (default: 7000)')
        print('')
        print('Note: Data connections will use port + 1 (e.g., 7001 if control port is 7000)')
        print('')
        print('Example:')
        print('  frps 7000')
        print('')
        print('Features:')
        print('  - Dynamic port mapping: Server automatically listens on same ports as client')
        print('  - Auto port registration: Client scans local ports and notifies server')
        print('  - Separated control and data channels for better reliability')
        print('  - Ultra high performance: 4MB buffer, TCP window optimization')
        print('  - Detailed logging and performance monitoring')
        print('  - Connection pooling and keep-alive')
        sys.exit(1)
    
    try:
        frps_port = int(sys.argv[1])
        
        print(f'FRPS Server v2.4')
        print(f'Control port: {frps_port}')
        print(f'Data port: {frps_port + 1}')
        print('Dynamic port mapping enabled')
        print('Performance monitoring enabled')
        print('Ultra high performance mode (4MB buffer)')
        print('')
        
        Frps(frps_port=frps_port).start()
        
    except ValueError:
        print('Error: Port must be an integer')
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info('Shutting down...')
        sys.exit(0)


if __name__ == '__main__':
    main()
