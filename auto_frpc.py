#!/usr/bin/env python
import sys
import time
import logging
import threading
from collections import defaultdict

import port_scanner
import frpc

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('AutoFrpc')


class AutoFrpcManager:
    def __init__(self, server_host, server_port, target_host='localhost', 
                 scan_interval=30, pool_size=5, ports=None, min_stable_time=10):
        self.server_host = server_host
        self.server_port = server_port
        self.target_host = target_host
        self.scan_interval = scan_interval
        self.pool_size = pool_size
        self.monitored_ports = ports or []
        self.min_stable_time = min_stable_time
        
        self.active_connections = {}
        self.port_stability = defaultdict(list)
        self.running = False
        self.lock = threading.Lock()
        
        self.scanner = port_scanner.PortScanner(
            scan_interval=self.scan_interval,
            custom_ports=self.monitored_ports if self.monitored_ports else None
        )

    def is_port_stable(self, port):
        now = time.time()
        with self.lock:
            history = self.port_stability[port]
            if not history:
                return False
            
            history[:] = [t for t in history if now - t <= self.min_stable_time]
            return len(history) >= 2

    def create_frpc_connection(self, target_port, proxy_port=None):
        if proxy_port is None:
            proxy_port = target_port
        
        try:
            logger.info(f'Creating FRPC connection for port {target_port}')
            
            connection_key = f'{target_port}:{proxy_port}'
            
            if connection_key in self.active_connections:
                logger.warning(f'Connection {connection_key} already exists')
                return False
            
            frpc_instance = frpc.Frpc(
                server_host=self.server_host,
                server_port=self.server_port,
                target_host=self.target_host,
                target_port=target_port,
                pool_size=self.pool_size
            )
            
            thread = threading.Thread(
                target=frpc_instance.run,
                daemon=True,
                name=f'FRPC-{target_port}-{proxy_port}'
            )
            thread.start()
            
            with self.lock:
                self.active_connections[connection_key] = {
                    'instance': frpc_instance,
                    'thread': thread,
                    'target_port': target_port,
                    'proxy_port': proxy_port,
                    'created_at': time.time()
                }
            
            logger.info(f'Successfully created FRPC connection for port {target_port}')
            return True
            
        except Exception as e:
            logger.error(f'Failed to create FRPC connection for port {target_port}: {e}')
            return False

    def remove_frpc_connection(self, target_port, proxy_port=None):
        if proxy_port is None:
            proxy_port = target_port
        
        connection_key = f'{target_port}:{proxy_port}'
        
        with self.lock:
            if connection_key not in self.active_connections:
                logger.warning(f'Connection {connection_key} not found')
                return False
            
            conn_info = self.active_connections[connection_key]
            try:
                conn_info['instance'].stop()
                logger.info(f'Stopped FRPC connection for port {target_port}')
            except Exception as e:
                logger.error(f'Error stopping FRPC connection: {e}')
            
            del self.active_connections[connection_key]
            return True

    def handle_scan_results(self, scan_result):
        active_ports = scan_result['active_ports']
        new_ports = scan_result['new_ports']
        closed_ports = scan_result['closed_ports']
        
        now = time.time()
        
        for port in active_ports:
            with self.lock:
                self.port_stability[port].append(now)
            
            if self.is_port_stable(port):
                self.create_frpc_connection(port)
        
        for port in closed_ports:
            with self.lock:
                if port in self.port_stability:
                    del self.port_stability[port]
            
            self.remove_frpc_connection(port)

    def monitor_ports(self):
        logger.info('Starting automatic FRPC monitoring')
        
        while self.running:
            try:
                scan_result = self.scanner.scan(host=self.target_host)
                self.handle_scan_results(scan_result)
                
                time.sleep(self.scan_interval)
                
            except Exception as e:
                logger.error(f'Error in monitoring loop: {e}')
                time.sleep(5)

    def start(self):
        self.running = True
        logger.info('Auto FRPC Manager starting...')
        
        monitor_thread = threading.Thread(
            target=self.monitor_ports,
            daemon=True,
            name='AutoFrpcMonitor'
        )
        monitor_thread.start()
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info('Received interrupt, shutting down...')
            self.stop()

    def stop(self):
        self.running = False
        
        with self.lock:
            for connection_key, conn_info in list(self.active_connections.items()):
                try:
                    conn_info['instance'].stop()
                    logger.info(f'Stopped connection {connection_key}')
                except Exception as e:
                    logger.error(f'Error stopping connection {connection_key}: {e}')
        
        self.active_connections.clear()
        logger.info('Auto FRPC Manager stopped')

    def get_status(self):
        with self.lock:
            status = {
                'active_connections': len(self.active_connections),
                'connections': []
            }
            
            for connection_key, conn_info in self.active_connections.items():
                status['connections'].append({
                    'key': connection_key,
                    'target_port': conn_info['target_port'],
                    'proxy_port': conn_info['proxy_port'],
                    'running': conn_info['thread'].is_alive(),
                    'uptime': time.time() - conn_info['created_at']
                })
            
            return status


def main():
    if len(sys.argv) < 3:
        print('Usage: python auto_frpc.py <server_host> <server_port> [options]')
        print('')
        print('Options:')
        print('  --target HOST        Target host to scan (default: localhost)')
        print('  --interval SECONDS    Scan interval in seconds (default: 30)')
        print('  --pool-size NUM       Connection pool size (default: 5)')
        print('  --ports PORTS        Comma-separated ports to monitor (default: all ports)')
        print('  --stable-time SECONDS Port stability time (default: 10)')
        print('  --status             Show current status and exit')
        print('')
        print('Examples:')
        print('  python auto_frpc.py 192.168.1.100 7000')
        print('  python auto_frpc.py 192.168.1.100 7000 --ports 22,80,3389')
        print('  python auto_frpc.py 192.168.1.100 7000 --interval 60 --pool-size 10')
        sys.exit(1)
    
    server_host = sys.argv[1]
    server_port = int(sys.argv[2])
    
    target_host = 'localhost'
    scan_interval = 30
    pool_size = 5
    ports = None
    min_stable_time = 10
    show_status = False
    
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
        elif arg == '--stable-time' and i + 1 < len(sys.argv):
            min_stable_time = int(sys.argv[i + 1])
            i += 2
        elif arg == '--status':
            show_status = True
            i += 1
        else:
            print(f'Unknown option: {arg}')
            sys.exit(1)
    
    manager = AutoFrpcManager(
        server_host=server_host,
        server_port=server_port,
        target_host=target_host,
        scan_interval=scan_interval,
        pool_size=pool_size,
        ports=ports,
        min_stable_time=min_stable_time
    )
    
    if show_status:
        import json
        status = manager.get_status()
        print(json.dumps(status, indent=2))
        return
    
    manager.start()


if __name__ == '__main__':
    main()
