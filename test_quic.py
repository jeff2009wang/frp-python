#!/usr/bin/env python
import sys
import socket
import threading
import time

def start_test_server(port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('127.0.0.1', port))
    server.listen(5)
    print(f'Test server listening on port {port}')
    
    try:
        while True:
            conn, addr = server.accept()
            print(f'Connection from {addr}')
            
            try:
                conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nHello from test server!')
            except Exception as e:
                print(f'Error sending data: {e}')
            finally:
                conn.close()
    except KeyboardInterrupt:
        print('Test server stopped')
    finally:
        server.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python test_quic.py <port>')
        print('Example: python test_quic.py 8080')
        sys.exit(1)
    
    port = int(sys.argv[1])
    start_test_server(port)
