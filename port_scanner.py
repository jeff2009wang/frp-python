#!/usr/bin/env python
import socket
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('PortScanner')


class PortScanner:
    def __init__(self, scan_interval=30, custom_ports=None, max_workers=100):
        self.scan_interval = scan_interval
        self.custom_ports = custom_ports or []
        self.max_workers = max_workers
        self.active_ports = set()
        self.running = False
        self.lock = threading.Lock()

    def check_port(self, host, port, timeout=0.5):
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
                ports = range(1, 65536)
        
        logger.info(f'Scanning {len(list(ports))} ports with {self.max_workers} workers...')
        
        active_ports = set()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_port = {
                executor.submit(self.check_port, host, port, 0.5): port 
                for port in ports
            }
            
            for future in as_completed(future_to_port):
                port = future_to_port[future]
                try:
                    if future.result():
                        active_ports.add(port)
                        logger.info(f'Found active service on port {port}')
                except Exception as e:
                    logger.debug(f'Error scanning port {port}: {e}')
        
        return sorted(active_ports)

    def scan(self, host='127.0.0.1'):
        logger.info('Starting port scan...')
        
        current_active = set(self.scan_ports_fast(host))
        
        with self.lock:
            new_ports = current_active - self.active_ports
            closed_ports = self.active_ports - current_active
            
            for port in new_ports:
                logger.info(f'New service detected on port {port}')
            
            for port in closed_ports:
                logger.info(f'Service closed on port {port}')
            
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
                logger.error(f'Error during scan: {e}')
            
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


if __name__ == '__main__':
    import sys
    
    scan_interval = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    ports = None
    max_workers = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    
    if len(sys.argv) > 2:
        try:
            ports = [int(p) for p in sys.argv[2].split(',')]
        except ValueError:
            print('Ports must be comma-separated integers')
            sys.exit(1)
    
    scanner = PortScanner(
        scan_interval=scan_interval,
        custom_ports=ports,
        max_workers=max_workers
    )
    
    try:
        scanner.start_continuous_scan()
    except KeyboardInterrupt:
        print('\nStopping scanner...')
        scanner.stop()
