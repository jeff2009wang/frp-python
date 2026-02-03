# frp_core_single.pyx
# 单文件Cython加速模块 - 直接编译即可使用

# cython: language_level=3
#cython: boundscheck=False
#cython: wraparound=False
#cython: initializedcheck=False
#cython: cdivision=True
#cython: infer_types=True

import socket
import struct
import time
import logging
from libc.string cimport memcpy
from libc.stdint cimport uint8_t, uint32_t, uint64_t

ctypedef struct DataHeader:
    uint32_t length
    uint32_t conn_id

cdef void pack_header_nogil(uint8_t* buffer, uint32_t length, uint32_t conn_id) nogil except *:
    buffer[0] = (length >> 24) & 0xFF
    buffer[1] = (length >> 16) & 0xFF
    buffer[2] = (length >> 8) & 0xFF
    buffer[3] = length & 0xFF
    buffer[4] = (conn_id >> 24) & 0xFF
    buffer[5] = (conn_id >> 16) & 0xFF
    buffer[6] = (conn_id >> 8) & 0xFF
    buffer[7] = conn_id & 0xFF

cdef class FastForwarder:
    cdef readonly int stream_id
    cdef readonly int conn_id
    cdef object _socket  # Python socket对象
    cdef uint8_t[8] _header_buffer
    cdef int _buffer_size
    cdef object _quic_conn
    cdef object _logger
    cdef float _last_log_time
    
    def __init__(self, stream_id, conn_id, socket_obj, quic_conn, buffer_size=1024*1024):
        self.stream_id = stream_id
        self.conn_id = conn_id
        self._socket = socket_obj
        self._quic_conn = quic_conn
        self._buffer_size = buffer_size
        self._logger = logging.getLogger(f'FastForwarder-{stream_id}')
        self._last_log_time = time.time()
        
        pack_header_nogil(self._header_buffer, 0, conn_id)
    
    cpdef uint64_t forward_loop(self) except? 0:
        cdef uint64_t total_bytes = 0
        cdef bytes data
        cdef int data_len
        cdef uint8_t[8] header
        cdef float current_time
        cdef bytes header_bytes
        
        while True:
            try:
                data = self._socket.recv(self._buffer_size)
                data_len = len(data)
                if data_len == 0:
                    break
                
                total_bytes += data_len
                
                current_time = time.time()
                if total_bytes % (10 * 1024 * 1024) == 0 and (current_time - self._last_log_time >= 1.0):
                    self._logger.info(f'Forwarded {data_len} bytes on stream {self.stream_id} (total: {total_bytes // 1024}KB)')
                    self._last_log_time = current_time
                
                pack_header_nogil(header, data_len, self.conn_id)
                header_bytes = header[:8]
                
                self._quic_conn.send_stream_data(self.stream_id, header_bytes + data)
                self._quic_conn.transmit()
                
            except Exception as e:
                self._logger.error(f'Error in forward loop: {e}')
                break
        
        self._logger.info(f'Stream {self.stream_id} finished, transferred {total_bytes} bytes')
        return total_bytes

def create_fast_forwarder(stream_id, conn_id, socket_obj, quic_conn, buffer_size=1024*1024):
    return FastForwarder(stream_id, conn_id, socket_obj, quic_conn, buffer_size)


# 纯Python回退版本
class PythonForwarder:
    def __init__(self, stream_id, conn_id, socket_obj, quic_conn, buffer_size=1024*1024):
        self.stream_id = stream_id
        self.conn_id = conn_id
        self._socket = socket_obj
        self._quic_conn = quic_conn
        self._buffer_size = buffer_size
        self._logger = logging.getLogger(f'PythonForwarder-{stream_id}')
        self._last_log_time = time.time()
        self._conn_id_bytes = struct.pack('!i', conn_id)
    
    def forward_loop(self):
        total_bytes = 0
        while True:
            try:
                data = self._socket.recv(self._buffer_size)
                if not data:
                    break
                
                total_bytes += len(data)
                
                current_time = time.time()
                if total_bytes % (10 * 1024 * 1024) == 0 and (current_time - self._last_log_time >= 1.0):
                    self._logger.info(f'Forwarded {len(data)} bytes on stream {self.stream_id} (total: {total_bytes // 1024}KB)')
                    self._last_log_time = current_time
                
                header = struct.pack('!i', len(data)) + self._conn_id_bytes
                self._quic_conn.send_stream_data(self.stream_id, header + data)
                self._quic_conn.transmit()
                
            except Exception as e:
                self._logger.error(f'Error in forward loop: {e}')
                break
        
        self._logger.info(f'Stream {self.stream_id} finished, transferred {total_bytes} bytes')
        return total_bytes


# 智能选择函数
def create_forwarder(stream_id, conn_id, socket_obj, quic_conn, buffer_size=1024*1024, force_python=False):
    if force_python:
        return PythonForwarder(stream_id, conn_id, socket_obj, quic_conn, buffer_size)
    else:
        try:
            return FastForwarder(stream_id, conn_id, socket_obj, quic_conn, buffer_size)
        except:
            return PythonForwarder(stream_id, conn_id, socket_obj, quic_conn, buffer_size)


# 性能测试函数
def run_performance_test(buffer_size=1024*1024, iterations=100000):
    import time
    cdef uint8_t[8] header
    cdef int i
    cdef uint32_t length = 1024
    cdef uint32_t conn_id = 12345
    
    start = time.time()
    for i in range(iterations):
        pack_header_nogil(header, length, conn_id)
    elapsed = time.time() - start
    
    if elapsed > 0:
        print(f"Cython pack performance: {iterations/elapsed:.0f} packs/sec")
        print(f"Per iteration: {elapsed/iterations*1000000:.2f} microseconds")
    else:
        print(f"Cython pack performance: {iterations} packs in <{elapsed:.6f} sec")
    
    return iterations / elapsed if elapsed > 0 else 0
