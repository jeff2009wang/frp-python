# cython: language_level=3
#cython: boundscheck=False
#cython: wraparound=False
#cython: initializedcheck=False
#cython: cdivision=True

import socket
import struct
from cython cimport view
from libc.string cimport memcpy

ctypedef signed char int8_t
ctypedef unsigned char uint8_t
ctypedef short int16_t
ctypedef unsigned short uint16_t
ctypedef int int32_t
ctypedef unsigned int uint32_t
ctypedef long long int64_t
ctypedef unsigned long long uint64_t


cdef class FastDataForwarder:
    cdef int stream_id
    cdef int conn_id
    cdef socket.socket _conn
    cdef uint8_t[8] header_buffer
    cdef int conn_id_int
    
    def __init__(self, stream_id, conn_id, conn):
        self.stream_id = stream_id
        self.conn_id_int = conn_id
        self._conn = conn
        
        struct.pack_into('!i', self.header_buffer, 4, conn_id)
    
    cpdef bytes pack_header(self, int data_len):
        struct.pack_into('!i', self.header_buffer, 0, data_len)
        return self.header_buffer[:8]
    
    cpdef int forward_data(self, quic_conn, int buffer_size=1024*1024) except? -1:
        cdef char[1024*1024] buffer
        cdef int total_bytes = 0
        cdef int data_len
        cdef bytes header
        cdef bytes data
        
        while True:
            try:
                data = self._conn.recv(buffer_size)
                data_len = len(data)
                if data_len == 0:
                    return total_bytes
                
                total_bytes += data_len
                header = self.pack_header(data_len)
                quic_conn.send_stream_data(self.stream_id, header + data)
                quic_conn.transmit()
                
            except Exception:
                break
        
        return total_bytes


cdef inline void pack_header_inline(uint8_t* header, int32_t data_len, int32_t conn_id) nogil:
    header[0] = (data_len >> 24) & 0xFF
    header[1] = (data_len >> 16) & 0xFF
    header[2] = (data_len >> 8) & 0xFF
    header[3] = data_len & 0xFF
    header[4] = (conn_id >> 24) & 0xFF
    header[5] = (conn_id >> 16) & 0xFF
    header[6] = (conn_id >> 8) & 0xFF
    header[7] = conn_id & 0xFF


cdef class UltraFastForwarder:
    cdef int stream_id
    cdef int conn_id
    cdef socket.socket _conn
    cdef uint8_t[8] header_buffer
    cdef int buffer_size
    
    def __init__(self, stream_id, conn_id, conn, buffer_size=1024*1024):
        self.stream_id = stream_id
        self.conn_id = conn_id
        self._conn = conn
        self.buffer_size = buffer_size
        pack_header_inline(self.header_buffer, 0, conn_id)
    
    cpdef int forward_loop(self, quic_conn) except? -1:
        cdef int total_bytes = 0
        cdef bytes data
        cdef int data_len
        cdef uint8_t[8] header
        
        while True:
            try:
                data = self._conn.recv(self.buffer_size)
                data_len = len(data)
                if data_len == 0:
                    return total_bytes
                
                total_bytes += data_len
                
                pack_header_inline(header, data_len, self.conn_id)
                quic_conn.send_stream_data(
                    self.stream_id, 
                    header[:8] + data
                )
                quic_conn.transmit()
                
            except Exception:
                break
        
        return total_bytes


def create_forwarder(stream_id, conn_id, conn, buffer_size=1024*1024):
    return UltraFastForwarder(stream_id, conn_id, conn, buffer_size)
