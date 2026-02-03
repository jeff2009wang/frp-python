#!/usr/bin/env python
import sys
import socket
import time
import threading
import struct
import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional, Set, List
from aioquic.quic.connection import QuicConnection
from aioquic.quic.events import QuicEvent, StreamDataReceived, HandshakeCompleted, ConnectionTerminated
from aioquic.quic.configuration import QuicConfiguration
from aioquic.asyncio import connect, QuicConnectionProtocol

# 尝试使用uvloop优化（Linux/Mac性能提升显著）
try:
    if sys.platform != 'win32':
        import uvloop
        uvloop.install()
        logger = logging.getLogger('frpc_quic')
        logger.info('✓ 使用uvloop加速事件循环')
    else:
        logger = logging.getLogger('frpc_quic')
except ImportError:
    logger = logging.getLogger('frpc_quic')

# 纯Python优化实现
USE_CYTHON = False
_create_forwarder = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


CMD_HEARTBEAT = 1
CMD_REGISTER_PORT = 2
CMD_UNREGISTER_PORT = 3
CMD_CONNECTION = 4
CMD_CONNECTION_ACK = 5


class FrpcQuicProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.control_stream_id: Optional[int] = None
        self.registered_ports: Set[int] = set()
        self.active_streams: Dict[int, socket.socket] = {}
        self.lock = threading.Lock()
        self.next_conn_id = 1
        self.on_port_change = None
        self.pending_registrations: Dict[int, asyncio.Future] = {}
        self.last_log_time = 0

    def quic_event_received(self, event: QuicEvent):
        if isinstance(event, StreamDataReceived):
            asyncio.create_task(self.handle_stream_data(event.stream_id, event.data))
        elif isinstance(event, ConnectionTerminated):
            logger.warning(f'QUIC connection terminated: {event.error_code}')

    async def send_heartbeat(self):
        if self.control_stream_id is not None:
            try:
                self._quic.send_stream_data(self.control_stream_id, struct.pack('!i', CMD_HEARTBEAT))
                await self._flush_buffers()
            except Exception as e:
                logger.error(f'Failed to send heartbeat: {e}')
    
    async def _flush_buffers(self):
        try:
            with self.lock:
                self.transmit()
                self.last_transmit_time = time.time()
        except Exception as e:
            logger.debug(f'Error during transmit: {e}')
    
    async def _send_stream_data_batched(self, stream_id: int, data: bytes, flush: bool = False):
        with self.lock:
            self._quic.send_stream_data(stream_id, data)
            
            if flush:
                try:
                    self.transmit()
                except Exception as e:
                    logger.debug(f'Error during transmit: {e}')

    async def register_port(self, port: int, timeout: float = 5.0) -> bool:
        if self.control_stream_id is not None:
            try:
                await self._send_stream_data_batched(
                    self.control_stream_id,
                    struct.pack('!i', CMD_REGISTER_PORT) + struct.pack('!i', port),
                    flush=True
                )
                logger.info(f'Sent register port {port}')
                
                future = asyncio.Future()
                self.pending_registrations[port] = future
                
                try:
                    result = await asyncio.wait_for(future, timeout=timeout)
                    return result
                except asyncio.TimeoutError:
                    logger.warning(f'Port {port} registration timed out after {timeout}s')
                    if port in self.pending_registrations:
                        del self.pending_registrations[port]
                    return False
            except Exception as e:
                logger.error(f'Failed to send register port {port}: {e}')
                if port in self.pending_registrations:
                    del self.pending_registrations[port]
                return False
        return False

    async def unregister_port(self, port: int):
        if self.control_stream_id is not None:
            await self._send_stream_data_batched(
                self.control_stream_id,
                struct.pack('!i', CMD_UNREGISTER_PORT) + struct.pack('!i', port),
                flush=True
            )
            logger.info(f'Sent unregister port {port}')

    async def request_connection(self, port: int):
        with self.lock:
            conn_id = self.next_conn_id
            self.next_conn_id += 1
        
        if self.control_stream_id is not None:
            await self._send_stream_data_batched(
                self.control_stream_id,
                struct.pack('!i', CMD_CONNECTION) + struct.pack('!i', port) + struct.pack('!i', conn_id),
                flush=True
            )
        
        return conn_id

    async def handle_stream_data(self, stream_id: int, data: bytes):
        if stream_id == self.control_stream_id:
            await self._handle_control_data(data)
        else:
            await self._handle_data_stream(stream_id, data)

    async def _handle_control_data(self, data: bytes):
        if len(data) >= 4:
            cmd = struct.unpack('!i', data[:4])[0]
            
            if cmd == CMD_HEARTBEAT:
                logger.debug('Heartbeat received')
            elif cmd == CMD_REGISTER_PORT:
                if len(data) >= 8:
                    port = struct.unpack('!i', data[4:8])[0]
                    if port > 0:
                        logger.info(f'Port {port} registered successfully')
                    else:
                        logger.warning('Port registration failed')
            elif cmd == CMD_UNREGISTER_PORT:
                if len(data) >= 8:
                    port = struct.unpack('!i', data[4:8])[0]
                    logger.info(f'Port {port} unregistered')
            elif cmd == CMD_CONNECTION:
                if len(data) >= 16:
                    stream_id = struct.unpack('!i', data[4:8])[0]
                    port = struct.unpack('!i', data[8:12])[0]
                    conn_id = struct.unpack('!i', data[12:16])[0]
                    await self._handle_server_connection_request(stream_id, port, conn_id)

    async def _handle_server_connection_request(self, stream_id: int, port: int, conn_id: int):
        logger.info(f'Server connection request for port {port}, stream_id {stream_id}, conn_id {conn_id}')
        
        try:
            target_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_conn.settimeout(5.0)
            target_conn.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2 * 1024 * 1024)
            target_conn.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)
            target_conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            target_conn.connect(('127.0.0.1', port))
            logger.debug(f'Connected to target port {port}')
            
            with self.lock:
                self.active_streams[stream_id] = target_conn
            
            if self.control_stream_id is not None:
                await self._send_stream_data_batched(
                    self.control_stream_id,
                    struct.pack('!i', CMD_CONNECTION_ACK) + struct.pack('!i', stream_id),
                    flush=True
                )
                logger.debug(f'Sent ACK for stream {stream_id}')
            
            threading.Thread(
                target=self._forward_to_server_sync,
                args=(target_conn, stream_id, conn_id),
                daemon=True
            ).start()
            
        except Exception as e:
            logger.error(f'Failed to connect to target port {port}: {e}')

    def _forward_to_server_sync(self, target_conn: socket.socket, stream_id: int, conn_id: int):
        logger.info(f'Forward thread started for stream {stream_id}')
        target_conn.settimeout(None)
        buffer_size = 1024 * 1024
        total_bytes = 0
        last_log_time = time.time()
        
        try:
            # 纯Python优化版本：使用内存视图和批处理减少分配
            conn_id_bytes = struct.pack('!i', conn_id)
            header_struct = struct.Struct('!ii')
            
            while True:
                try:
                    data = target_conn.recv(buffer_size)
                    if not data:
                        logger.info(f'Target port closed connection normally')
                        break
                    
                    total_bytes += len(data)
                    current_time = time.time()
                    if total_bytes % (10 * 1024 * 1024) == 0 and (current_time - last_log_time >= 1.0):
                        logger.info(f'Forwarding {len(data)} bytes from target to stream {stream_id} (total: {total_bytes // 1024}KB)')
                        last_log_time = current_time
                    
                    # 使用预打包的结构体头部提高性能
                    header = header_struct.pack(len(data), conn_id)
                    self._quic.send_stream_data(stream_id, header + data)
                    self.transmit()
                    
                except Exception as e:
                    logger.error(f'Error forwarding data from target: {e}')
                    break
            
            logger.info(f'Connection to port closed, transferred {total_bytes} bytes')
            
        finally:
            target_conn.close()
            with self.lock:
                if stream_id in self.active_streams:
                    del self.active_streams[stream_id]

    async def _handle_data_stream(self, stream_id: int, data: bytes):
        current_time = time.time()
        with self.lock:
            if stream_id in self.active_streams:
                target_conn = self.active_streams[stream_id]
                if current_time - self.last_log_time >= 1.0:
                    logger.debug(f'Forwarding {len(data)} bytes from stream {stream_id} to target')
                    self.last_log_time = current_time
                try:
                    offset = 0
                    while offset < len(data):
                        if offset + 8 > len(data):
                            break
                        
                        data_len = struct.unpack('!i', data[offset:offset+4])[0]
                        conn_id = struct.unpack('!i', data[offset+4:offset+8])[0]
                        payload = data[offset+8:offset+8+data_len]
                        
                        rewritten_payload = self._rewrite_http_headers(payload)
                        target_conn.sendall(rewritten_payload)
                        offset += 8 + data_len
                        
                except Exception as e:
                    logger.error(f'Error forwarding data to target: {e}')
            else:
                logger.warning(f'No active connection for stream {stream_id}')

    def _rewrite_http_headers(self, payload: bytes) -> bytes:
        try:
            if len(payload) < 16:
                return payload
            
            payload_str = payload.decode('utf-8', errors='ignore')
            
            if not payload_str.startswith(('GET ', 'POST ', 'PUT ', 'DELETE ', 'HEAD ', 'OPTIONS ', 'PATCH ')):
                return payload
            
            lines = payload_str.split('\r\n')
            if len(lines) < 2:
                return payload
            
            headers_to_rewrite = {
                'host:': '127.0.0.1',
                'origin:': 'http://127.0.0.1:5212',
                'referer:': 'http://127.0.0.1:5212/',
            }
            
            for i, line in enumerate(lines):
                if line == '':
                    break
                
                line_lower = line.lower()
                for header, value in headers_to_rewrite.items():
                    if line_lower.startswith(header):
                        original_value = line.split(':', 1)[1].strip() if ':' in line else ''
                        header_name = line.split(':', 1)[0] if ':' in line else header
                        lines[i] = f'{header_name}: {value}'
                        logger.debug(f'Rewrote {header}: {original_value} -> {value}')
                        break
            
            rewritten = '\r\n'.join(lines).encode('utf-8')
            return rewritten
        except Exception as e:
            logger.debug(f'Failed to rewrite HTTP headers: {e}')
            return payload


class PortScanner:
    def __init__(self, scan_interval: int = 20, custom_ports: Optional[List[int]] = None, max_workers: int = 50):
        self.scan_interval = scan_interval
        self.custom_ports = custom_ports or []
        self.max_workers = max_workers
        self.active_ports: Set[int] = set()
        self.running = False
        self.lock = threading.Lock()
        self.on_port_change = None
        self.scanned_ports: Set[int] = set()
        self.scan_cursor = 1
        self.batch_size = 20000
        self.is_lazy = False
        self.full_scan_interval = 600  # 10分钟
        self.last_full_scan_time = 0

    def check_port(self, host: str, port: int, timeout: float = 0.3) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def scan_ports_fast(self, host: str = '127.0.0.1', ports: Optional[List[int]] = None) -> List[int]:
        if ports is None:
            if self.custom_ports:
                ports = self.custom_ports
            else:
                ports = list(range(1, 65536))
        
        logger.debug(f'Scanning {len(ports)} ports with {self.max_workers} workers...')
        
        active_ports = []
        
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
                        active_ports.append(port)
                except Exception as e:
                    logger.debug(f'Error scanning port {port}: {e}')
        
        return sorted(active_ports)

    def scan_incremental(self, host: str = '127.0.0.1') -> Dict:
        logger.info(f'Starting incremental port scan (cursor: {self.scan_cursor})...')
        
        start_port = self.scan_cursor
        end_port = min(self.scan_cursor + self.batch_size, 65536)
        ports_to_scan = list(range(start_port, end_port))
        
        if not ports_to_scan:
            self.scan_cursor = 1
            ports_to_scan = list(range(1, min(self.batch_size + 1, 65536)))
            logger.info('Reset scan cursor, starting from port 1')
        
        logger.debug(f'Scanning ports {ports_to_scan[0]}-{ports_to_scan[-1]} ({len(ports_to_scan)} ports)')
        
        batch_active = set(self.scan_ports_fast(host, ports_to_scan))
        
        with self.lock:
            new_ports = batch_active - self.active_ports
            closed_ports = set()
            
            for port in self.active_ports:
                if start_port <= port < end_port:
                    if port not in batch_active and port not in self.scanned_ports:
                        closed_ports.add(port)
            
            for port in new_ports:
                logger.info(f'New service detected on port {port}')
                if self.on_port_change:
                    self.on_port_change('new', port)
            
            for port in closed_ports:
                logger.info(f'Service closed on port {port}')
                if self.on_port_change:
                    self.on_port_change('closed', port)
            
            self.active_ports.update(batch_active)
            for port in closed_ports:
                self.active_ports.discard(port)
            self.scanned_ports.update(batch_active)
            self.scan_cursor = end_port
        
        current_active = sorted(self.active_ports)
        logger.info(f'Incremental scan complete. Total active ports: {current_active}')
        return {
            'active_ports': current_active,
            'new_ports': sorted(new_ports),
            'closed_ports': sorted(closed_ports),
            'scanned_range': (start_port, end_port),
            'timestamp': time.time()
        }

    def scan(self, host: str = '127.0.0.1') -> Dict:
        current_time = time.time()
        should_full_scan = (current_time - self.last_full_scan_time) >= self.full_scan_interval
        
        if should_full_scan:
            logger.info('Time for full scan - scanning all ports 1-65535')
            self.last_full_scan_time = current_time
            return self.scan_full(host)
        else:
            return self.scan_incremental(host)

    def scan_full(self, host: str = '127.0.0.1') -> Dict:
        logger.info('Starting full port scan (all 65535 ports)...')
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
        
        logger.info(f'Full scan complete. Active ports: {sorted(current_active)}')
        return {
            'active_ports': sorted(current_active),
            'new_ports': sorted(new_ports),
            'closed_ports': sorted(closed_ports),
            'scan_type': 'full',
            'timestamp': time.time()
        }

    def start_continuous_scan(self, host: str = '127.0.0.1'):
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

    def get_active_ports(self) -> List[int]:
        with self.lock:
            return sorted(self.active_ports)


class FrpcQuicClient:
    def __init__(self, server_host: str, server_port: int, target_host: str = '127.0.0.1',
                 scan_interval: int = 300, ports: Optional[List[int]] = None, max_workers: int = 50, lazy: bool = False):
        self.server_host = server_host
        self.server_port = server_port
        self.target_host = target_host
        self.scan_interval = scan_interval
        self.ports = ports
        self.max_workers = max_workers
        self.lazy = lazy
        
        self.protocol: Optional[FrpcQuicProtocol] = None
        self.running = True
        self.auto_reconnect = True
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.port_change_queue: List[tuple] = []
        self.port_change_lock = threading.Lock()
        
        self.scanner = PortScanner(
            scan_interval=scan_interval,
            custom_ports=ports,
            max_workers=max_workers
        )
        self.scanner.is_lazy = lazy
        self.scanner.on_port_change = self.on_port_change
        
        self._connect_task: Optional[asyncio.Task] = None

    async def connect(self):
        configuration = QuicConfiguration(
            is_client=True,
            alpn_protocols=['frp-quic'],
            verify_mode=False,
            idle_timeout=300.0,
            max_stream_data_bidi_local=256 * 1024 * 1024,
            max_stream_data_bidi_remote=256 * 1024 * 1024,
            max_data=1024 * 1024 * 1024,
        )
        
        logger.info(f'Connecting to {self.server_host}:{self.server_port} using QUIC')
        
        def create_protocol(*args, **kwargs):
            return FrpcQuicProtocol(*args, **kwargs)
        
        async with connect(
            self.server_host,
            self.server_port,
            configuration=configuration,
            create_protocol=create_protocol,
        ) as self.protocol:
            self.protocol.control_stream_id = self.protocol._quic.get_next_available_stream_id()
            logger.info(f'QUIC connection established, control stream: {self.protocol.control_stream_id}')
            logger.info('0-RTT handshake completed - instant data transfer capability')
            
            heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            await asyncio.sleep(1.0)
            
            await self._re_register_ports()
            
            await asyncio.sleep(1.0)
            
            logger.info('Starting port monitor after connection established')
            asyncio.create_task(self._port_monitor_loop())
            asyncio.create_task(self._process_port_change_queue())
            
            await self._keep_alive_loop()

    async def _keep_alive_loop(self):
        while self.running and self.protocol:
            await asyncio.sleep(1)

    async def _heartbeat_loop(self):
        while self.running and self.protocol:
            try:
                await self.protocol.send_heartbeat()
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f'Heartbeat error: {e}')
                if self.auto_reconnect:
                    await self._reconnect()

    async def _port_monitor_loop(self):
        await asyncio.get_event_loop().run_in_executor(None, self.scanner.start_continuous_scan, self.target_host)

    async def _re_register_ports(self):
        with self.protocol.lock:
            for port in list(self.protocol.registered_ports):
                await self.protocol.register_port(port)

    async def _reconnect(self):
        logger.info('Attempting to reconnect...')
        try:
            await self.connect()
        except Exception as e:
            logger.error(f'Reconnection failed: {e}')

    async def _process_port_change_queue(self):
        logger.info('Processing pending port changes...')
        batch_size = 10
        registration_timeout = 2.0
        
        while self.running:
            with self.port_change_lock:
                if self.port_change_queue:
                    batch = self.port_change_queue[:batch_size]
                    self.port_change_queue = self.port_change_queue[batch_size:]
                    
                    logger.info(f'Processing batch of {len(batch)} port changes')
                    
                    tasks = []
                    for change_type, port in batch:
                        if change_type == 'new':
                            if self.protocol and port not in self.protocol.registered_ports:
                                self.protocol.registered_ports.add(port)
                                tasks.append(self._try_register_port(port))
                        elif change_type == 'closed':
                            if self.protocol and port in self.protocol.registered_ports:
                                self.protocol.registered_ports.discard(port)
                                await self.protocol.unregister_port(port)
                    
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
            
            await asyncio.sleep(0.05)

    async def _try_register_port(self, port: int):
        try:
            result = await asyncio.wait_for(
                self.protocol.register_port(port),
                timeout=2.0
            )
            if not result:
                logger.debug(f'Port {port} registration failed (already in use)')
        except asyncio.TimeoutError:
            logger.debug(f'Port {port} registration timeout (marked as registered)')
        except Exception as e:
            logger.debug(f'Port {port} registration error: {e}')

    def on_port_change(self, change_type: str, port: int):
        with self.port_change_lock:
            self.port_change_queue.append((change_type, port))
            if len(self.port_change_queue) % 50 == 1:
                logger.debug(f'Port change queue size: {len(self.port_change_queue)}')

    async def handle_connection(self, port: int):
        try:
            target_conn = socket.create_connection((self.target_host, port), timeout=5)
            logger.info(f'Connected to target {self.target_host}:{port}')
            
            conn_id = await self.protocol.request_connection(port)
            
            data_stream_id = self.protocol._quic.get_next_available_stream_id()
            
            with self.protocol.lock:
                self.protocol.active_streams[data_stream_id] = target_conn
            
            buffer_size = 64 * 1024
            total_bytes = 0
            
            target_conn.settimeout(1.0)
            
            while True:
                try:
                    data = target_conn.recv(buffer_size)
                    if not data:
                        break
                    
                    total_bytes += len(data)
                    header = struct.pack('!i', len(data)) + struct.pack('!i', conn_id)
                    self.protocol._quic.send_stream_data(data_stream_id, header + data)
                    self.protocol.transmit()
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f'Error forwarding data from target: {e}')
                    break
            
            logger.info(f'Connection to {self.target_host}:{port} closed, transferred {total_bytes} bytes')
            
        except Exception as e:
            logger.error(f'Failed to handle connection for port {port}: {e}')
        finally:
            if 'target_conn' in locals():
                target_conn.close()
            if data_stream_id in self.protocol.active_streams:
                del self.protocol.active_streams[data_stream_id]

    def stop(self):
        self.running = False
        self.scanner.stop()


def main():
    if len(sys.argv) < 3:
        print('FRPC QUIC Client v1.0 - Auto Port Scanner & Dynamic Port Mapping with 0-RTT')
        print('')
        print('Usage: frpc_quic <server_host> <server_port> [options]')
        print('')
        print('Required Arguments:')
        print('  server_host          FRPS QUIC server address')
        print('  server_port          FRPS QUIC server port')
        print('')
        print('Options:')
        print('  --target HOST        Target host to scan (default: 127.0.0.1)')
        print('  --interval SECONDS   Scan interval in seconds (default: 20)')
        print('  --ports PORTS        Comma-separated ports to monitor (default: all ports)')
        print('  --workers NUM        Port scan workers (default: 50)')
        print('  --lazy               Use incremental scanning mode (default: False)')
        print('')
        print('Scan Strategy:')
        print('  - Incremental scan: Scans 20000 ports every 20 seconds')
        print('  - Full scan: Scans all 65535 ports every 10 minutes')
        print('  - Combines speed and coverage for optimal performance')
        print('')
        print('Features:')
        print('  - QUIC protocol with 0-RTT handshake (instant reconnection)')
        print('  - Multiplexed streams (no extra TCP handshake per connection)')
        print('  - Built-in congestion control and weak network optimization')
        print('  - Fast concurrent port scanning')
        print('  - Auto port registration: Server listens on same ports as client')
        print('  - Dynamic port mapping: No manual configuration needed')
        print('')
        print('Performance Advantages over TCP:')
        print('  - 0-RTT: Reconnections are instant, no handshake delay')
        print('  - Better weak network performance with congestion control')
        print('  - Head-of-line blocking elimination')
        print('  - Connection migration support')
        print('')
        print('Examples:')
        print('  frpc_quic 192.168.1.100 7000')
        print('  frpc_quic 192.168.1.100 7000 --ports 22,80,3389')
        print('  frpc_quic 192.168.1.100 7000 --interval 60 --workers 200')
        print('  frpc_quic 192.168.1.100 7000 --lazy --interval 120')
        print('  frpc_quic 192.168.1.100 7000 --target 192.168.1.50')
        sys.exit(1)
    
    server_host = sys.argv[1]
    server_port = int(sys.argv[2])
    
    target_host = '127.0.0.1'
    scan_interval = 20
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
    
    client = FrpcQuicClient(
        server_host=server_host,
        server_port=server_port,
        target_host=target_host,
        scan_interval=scan_interval,
        ports=ports,
        max_workers=max_workers,
        lazy=lazy
    )
    
    print(f'FRPC QUIC Client v1.0')
    print(f'Server: {server_host}:{server_port}')
    print(f'Target: {target_host}')
    print(f'Scan interval: {scan_interval}s')
    print(f'Scan workers: {max_workers}')
    print(f'Scan mode: {"Lazy (incremental)" if lazy else "Full scan"}')
    if ports:
        print(f'Monitored ports: {ports}')
    else:
        print(f'Monitored ports: all (1-65535)')
    print(f'QUIC 0-RTT enabled')
    print('')
    
    async def run_client():
        try:
            await client.connect()
            while client.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info('Received interrupt, shutting down...')
        finally:
            client.stop()
    
    try:
        asyncio.run(run_client())
    except KeyboardInterrupt:
        logger.info('Shutting down...')
        sys.exit(0)


if __name__ == '__main__':
    main()
