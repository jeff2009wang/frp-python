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
logger = logging.getLogger('frpc')


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
    total_bytes = 0
    
    try:
        while True:
            try:
                data = conn_receiver.recv(PKT_BUFF_SIZE)
                if not data:
                    logger.debug(f'{direction}: Connection closed by receiver')
                    break
                
                data_len = len(data)
                total_bytes += data_len
                
                if direction == 'forward':
                    stats.add_sent(data_len)
                else:
                    stats.add_recv(data_len)
                
                last_activity = time.time()
                
                try:
                    conn_sender.sendall(data)
                except Exception as e:
                    logger.error(f'{direction}: Failed sending data ({data_len} bytes): {type(e).__name__}: {e}')
                    break
                    
            except socket.timeout:
                logger.warning(f'{direction}: Socket timeout')
                break
            except ConnectionResetError as e:
                logger.error(f'{direction}: Connection reset: {e}')
                break
            except BrokenPipeError as e:
                logger.error(f'{direction}: Broken pipe: {e}')
                break
            except Exception as e:
                logger.error(f'{direction}: Receive error ({total_bytes} bytes transferred): '
                          f'{type(e).__name__}: {e}')
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


class PortScanner:
    def __init__(self, scan_interval=300, custom_ports=None, max_workers=50):
        self.scan_interval = scan_interval
        self.custom_ports = custom_ports or []
        self.max_workers = max_workers
        self.active_ports = set()
        self.running = False
        self.lock = threading.Lock()
        self.on_port_change = None
        self.scanned_ports = set()
        self.scan_cursor = 1
        self.batch_size = 1000
        self.is_lazy = False

    def check_port(self, host, port, timeout=0.3):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def scan_ports_fast(self, host='127.0.0.1', ports=None):
        if ports is None:
            if self.custom_ports:
                ports = self.custom_ports
            else:
                ports = list(range(1, 65536))
        
        logger.debug(f'Scanning {len(ports)} ports with {self.max_workers} workers...')
        
        active_ports = set()
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_port = {
                executor.submit(self.check_port, host, port, 0.3): port 
                for port in ports
            }
            
            for future in as_completed(future_to_port):
                port = future_to_port[future]
                try:
                    if future.result():
                        active_ports.add(port)
                except Exception as e:
                    logger.debug(f'Error scanning port {port}: {e}')
        
        return sorted(active_ports)

    def scan_incremental(self, host='127.0.0.1'):
        logger.info('Starting incremental port scan...')
        
        start_port = self.scan_cursor
        end_port = min(self.scan_cursor + self.batch_size, 65536)
        ports_to_scan = list(range(start_port, end_port))
        
        if not ports_to_scan:
            self.scan_cursor = 1
            ports_to_scan = list(range(1, min(self.batch_size + 1, 65536)))
        
        logger.debug(f'Scanning ports {ports_to_scan[0]}-{ports_to_scan[-1]}')
        
        current_active = set(self.scan_ports_fast(host, ports_to_scan))
        
        with self.lock:
            new_ports = current_active - self.active_ports
            closed_ports = self.active_ports - current_active
            
            for port in new_ports:
                logger.info(f'New service detected on port {port}')
                if self.on_port_change:
                    self.on_port_change('new', port)
            
            for port in closed_ports:
                logger.info(f'Service closed on port {port}')
                if self.on_port_change:
                    self.on_port_change('closed', port)
            
            self.active_ports = current_active
            self.scanned_ports.update(current_active)
            self.scan_cursor = end_port
        
        logger.info(f'Incremental scan complete. Active ports: {sorted(current_active)}')
        return {
            'active_ports': sorted(current_active),
            'new_ports': sorted(new_ports),
            'closed_ports': sorted(closed_ports),
            'scanned_range': (start_port, end_port),
            'timestamp': time.time()
        }

    def scan(self, host='127.0.0.1'):
        if self.is_lazy:
            self.scan_incremental(host)
        else:
            logger.info('Starting full port scan...')
            current_active = set(self.scan_ports_fast(host))
            
            with self.lock:
                new_ports = current_active - self.active_ports
                closed_ports = self.active_ports - current_active
                
                for port in new_ports:
                    logger.info(f'New service detected on port {port}')
                    if self.on_port_change:
                        self.on_port_change('new', port)
                
                for port in closed_ports:
                    logger.info(f'Service closed on port {port}')
                    if self.on_port_change:
                        self.on_port_change('closed', port)
                
                self.active_ports = current_active
            
            logger.info(f'Scan complete. Active ports: {sorted(current_active)}')
            return {
                'active_ports': sorted(current_active),
                'new_ports': sorted(new_ports),
                'closed_ports': sorted(closed_ports),
                'timestamp': time.time()
            }

    def start_continuous_scan(self, host='127.0.0.1'):
        self.running = True
        logger.info(f'Starting continuous scan every {self.scan_interval} seconds')
        
        while self.running:
            try:
                self.scan(host)
            except Exception as e:
                logger.error(f'Error during scan: {type(e).__name__}: {e}')
            
            time.sleep(self.scan_interval)
        
        logger.info('Continuous scan stopped')

    def stop(self):
        self.running = False

    def get_active_ports(self):
        with self.lock:
            return sorted(self.active_ports)

    def is_port_active(self, port):
        with self.lock:
            return port in self.active_ports


class Frpc:
    def __init__(self, server_host, server_port, target_host='127.0.0.1', 
                 scan_interval=300, pool_size=5, ports=None, max_workers=50, lazy=False):
        self.server_host = server_host
        self.server_port = server_port
        self.data_port = server_port + 1
        self.target_host = target_host
        self.scan_interval = scan_interval
        self.pool_size = pool_size
        self.monitored_ports = ports
        self.max_workers = max_workers
        self.lazy = lazy
        
        self.control_fd = None
        self.running = True
        self.auto_reconnect = True
        self.registered_ports = set()
        self.lock = threading.Lock()
        
        self.scanner = PortScanner(
            scan_interval=scan_interval,
            custom_ports=ports,
            max_workers=max_workers
        )
        self.scanner.is_lazy = lazy
        self.scanner.on_port_change = self.on_port_change
        
        self.connect_to_server()
        threading.Thread(target=self.heartbeat, daemon=True).start()
        threading.Thread(target=self.port_monitor, daemon=True).start()

    def connect_to_server(self):
        retry_count = 0
        max_retries = 10
        retry_delay = 2
        
        while retry_count < max_retries and self.running:
            try:
                self.control_fd = socket.create_connection(
                    (self.server_host, self.server_port), timeout=5
                )
                optimize_socket(self.control_fd)
                
                self.control_fd.sendall(struct.pack('!i', CMD_HEARTBEAT))
                self.control_fd.setblocking(False)
                
                try:
                    sel.unregister(self.control_fd)
                except Exception:
                    pass
                sel.register(self.control_fd, selectors.EVENT_READ, self.handle_server_data)
                
                logger.info(f'Connected to server {self.server_host}:{self.server_port}')
                
                time.sleep(0.5)
                
                with self.lock:
                    for port in list(self.registered_ports):
                        self.send_register_port(port)
                
                return True
                
            except Exception as e:
                retry_count += 1
                logger.warning(f'Connection attempt {retry_count} failed: {type(e).__name__}: {e}')
                if retry_count < max_retries:
                    time.sleep(retry_delay)
        
        logger.error('Failed to connect to server after maximum retries')
        return False

    def heartbeat(self):
        while self.running:
            try:
                if self.control_fd is not None:
                    self.control_fd.sendall(struct.pack('!i', CMD_HEARTBEAT))
            except Exception as e:
                logger.error(f'Heartbeat failed: {type(e).__name__}: {e}')
                if self.auto_reconnect:
                    logger.info('Attempting to reconnect...')
                    self.reconnect()
            time.sleep(5)

    def send_register_port(self, port):
        try:
            self.control_fd.sendall(struct.pack('!i', CMD_REGISTER_PORT) + struct.pack('!i', port))
            logger.debug(f'Sent register port {port}')
        except Exception as e:
            logger.error(f'Failed to send register port {port}: {type(e).__name__}: {e}')

    def send_unregister_port(self, port):
        try:
            self.control_fd.sendall(struct.pack('!i', CMD_UNREGISTER_PORT) + struct.pack('!i', port))
            logger.debug(f'Sent unregister port {port}')
        except Exception as e:
            logger.error(f'Failed to send unregister port {port}: {type(e).__name__}: {e}')

    def on_port_change(self, change_type, port):
        if change_type == 'new':
            with self.lock:
                if port not in self.registered_ports:
                    self.registered_ports.add(port)
            self.send_register_port(port)
        elif change_type == 'closed':
            with self.lock:
                if port in self.registered_ports:
                    self.registered_ports.discard(port)
            self.send_unregister_port(port)

    def port_monitor(self):
        self.scanner.start_continuous_scan(self.target_host)

    def handle_server_data(self, control_fd, mask):
        try:
            data = control_fd.recv(4)
            if not data:
                logger.info('Server connection closed')
                if self.auto_reconnect:
                    self.reconnect()
                return
            
            cmd = struct.unpack('!i', data)[0]
            logger.debug(f'Received command: {cmd}')
            
            if cmd == CMD_HEARTBEAT:
                logger.debug('Heartbeat received')
                
            elif cmd == CMD_REGISTER_PORT:
                port_data = control_fd.recv(4)
                if port_data:
                    port = struct.unpack('!i', port_data)[0]
                    if port > 0:
                        logger.info(f'Port {port} registered on server')
                    else:
                        logger.warning(f'Port registration failed')
                
            elif cmd == CMD_UNREGISTER_PORT:
                port_data = control_fd.recv(4)
                if port_data:
                    port = struct.unpack('!i', port_data)[0]
                    logger.info(f'Port {port} unregistered on server')
                
            elif cmd == CMD_CONNECTION:
                port_data = control_fd.recv(4)
                if port_data:
                    port = struct.unpack('!i', port_data)[0]
                    logger.info(f'Received connection request for port {port}')
                    threading.Thread(target=self.handle_data_connection, args=(port,), daemon=True).start()
                        
        except Exception as e:
            logger.error(f'Error handling server data: {type(e).__name__}: {e}')
            if self.auto_reconnect:
                self.reconnect()

    def handle_data_connection(self, port):
        try:
            target_conn = socket.create_connection(
                (self.target_host, port), timeout=5
            )
            optimize_socket(target_conn)
            
            data_conn = socket.create_connection(
                (self.server_host, self.data_port), timeout=5
            )
            optimize_socket(data_conn)
            
            data_conn.sendall(struct.pack('!i', CMD_DATA_CONNECT) + struct.pack('!i', port))
            
            join(target_conn, data_conn)
            logger.info(f'Data connection established for port {port}')
            
        except Exception as e:
            logger.error(f'Failed to establish data connection for port {port}: {type(e).__name__}: {e}')

    def reconnect(self):
        try:
            if self.control_fd:
                sel.unregister(self.control_fd)
                self.control_fd.close()
        except Exception:
            pass
        
        self.control_fd = None
        logger.info('Reconnecting to server...')
        self.connect_to_server()

    def stop(self):
        self.running = False
        self.scanner.stop()
        if self.control_fd:
            try:
                sel.unregister(self.control_fd)
            except Exception:
                pass
            self.control_fd.close()

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
                            logger.error(f'Error in callback: {type(e).__name__}: {e}')
                except Exception as e:
                    logger.error(f'Error in select loop: {type(e).__name__}: {e}')
        except KeyboardInterrupt:
            logger.info('Received interrupt, shutting down...')
        finally:
            self.stop()


def main():
    if len(sys.argv) < 3:
        print('FRPC Client v2.3 - Auto Port Scanner & Dynamic Port Mapping')
        print('')
        print('Usage: frpc <server_host> <server_port> [options]')
        print('')
        print('Required Arguments:')
        print('  server_host          FRPS server address')
        print('  server_port          FRPS server control port')
        print('')
        print('Options:')
        print('  --target HOST        Target host to scan (default: 127.0.0.1)')
        print('  --interval SECONDS    Scan interval in seconds (default: 300)')
        print('  --pool-size NUM       Connection pool size (not used in v2)')
        print('  --ports PORTS        Comma-separated ports to monitor (default: all ports)')
        print('  --workers NUM        Port scan workers (default: 50)')
        print('  --lazy               Use incremental scanning mode (default: False)')
        print('')
        print('Note: Data connections will use server_port + 1')
        print('')
        print('Examples:')
        print('  frpc 192.168.1.100 7000')
        print('  frpc 192.168.1.100 7000 --ports 22,80,3389')
        print('  frpc 192.168.1.100 7000 --interval 60 --workers 200')
        print('  frpc 192.168.1.100 7000 --lazy --interval 120')
        print('  frpc 192.168.1.100 7000 --target 192.168.1.50')
        print('')
        print('Features:')
        print('  - Fast concurrent port scanning')
        print('  - Auto port registration: Server listens on same ports as client')
        print('  - Dynamic port mapping: No manual configuration needed')
        print('  - Separated control and data channels for better reliability')
        print('  - Low latency TCP optimization (1MB buffer, TCP_NODELAY)')
        print('  - Lazy scanning mode: Incremental scanning to reduce CPU usage')
        print('  - Detailed logging and performance monitoring')
        print('  - Auto reconnect on connection failure')
        sys.exit(1)
    
    server_host = sys.argv[1]
    server_port = int(sys.argv[2])
    
    target_host = '127.0.0.1'
    scan_interval = 300
    pool_size = 5
    ports = None
    max_workers = 50
    lazy = False
    
    i = 3
    while i < len(sys.argv):
        arg = sys.argv[i]
        
        if arg == '--target' and i + 1 < len(sys.argv):
            target_host = sys.argv[i + 1]
            i += 2
        elif arg == '--interval' and i + 1 < len(sys.argv):
            scan_interval = int(sys.argv[i + 1])
            i += 2
        elif arg == '--pool-size' and i + 1 < len(sys.argv):
            pool_size = int(sys.argv[i + 1])
            i += 2
        elif arg == '--ports' and i + 1 < len(sys.argv):
            ports = [int(p) for p in sys.argv[i + 1].split(',')]
            i += 2
        elif arg == '--workers' and i + 1 < len(sys.argv):
            max_workers = int(sys.argv[i + 1])
            i += 2
        elif arg == '--lazy':
            lazy = True
            i += 1
        else:
            print(f'Unknown option: {arg}')
            sys.exit(1)
    
    frpc_instance = Frpc(
        server_host=server_host,
        server_port=server_port,
        target_host=target_host,
        scan_interval=scan_interval,
        pool_size=pool_size,
        ports=ports,
        max_workers=max_workers,
        lazy=lazy
    )
    
    print(f'FRPC Client v2.4')
    print(f'Server: {server_host}:{server_port} (control), {server_host}:{server_port + 1} (data)')
    print(f'Target: {target_host}')
    print(f'Scan interval: {scan_interval}s')
    print(f'Scan workers: {max_workers}')
    print(f'Scan mode: {"Lazy (incremental)" if lazy else "Full scan"}')
    print(f'Performance monitoring enabled')
    print(f'Ultra high performance mode (4MB buffer)')
    if ports:
        print(f'Monitored ports: {ports}')
    else:
        print(f'Monitored ports: all (1-65535)')
    print('')
    
    frpc_instance.run()


if __name__ == '__main__':
    main()
