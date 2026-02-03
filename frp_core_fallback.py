import socket
import struct


class FastDataForwarder:
    def __init__(self, stream_id, conn_id, conn):
        self.stream_id = stream_id
        self.conn_id = conn_id
        self._conn = conn
        self.conn_id_bytes = struct.pack('!i', conn_id)
    
    def pack_header(self, data_len):
        return struct.pack('!i', data_len) + self.conn_id_bytes
    
    def forward_data(self, quic_conn, buffer_size=1024*1024):
        total_bytes = 0
        while True:
            try:
                data = self._conn.recv(buffer_size)
                if not data:
                    return total_bytes
                
                total_bytes += len(data)
                header = self.pack_header(len(data))
                quic_conn.send_stream_data(self.stream_id, header + data)
                quic_conn.transmit()
                
            except Exception:
                break
        
        return total_bytes


def create_forwarder(stream_id, conn_id, conn, buffer_size=1024*1024):
    return FastDataForwarder(stream_id, conn_id, conn)
