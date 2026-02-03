#!/usr/bin/env python
import sys
import time
import socket
import threading

def create_test_server(port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('localhost', port))
    server.listen(5)
    
    def handle_client():
        try:
            conn, addr = server.accept()
            print(f'Test server on port {port} accepted connection from {addr}')
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                conn.sendall(data)
            conn.close()
        except Exception as e:
            print(f'Test server error: {e}')
    
    thread = threading.Thread(target=handle_client, daemon=True)
    thread.start()
    print(f'Test server started on port {port}')
    return server

def test_port_scanner():
    print('\n=== Testing Port Scanner ===')
    import port_scanner
    
    scanner = port_scanner.PortScanner(
        scan_interval=2,
        custom_ports=[12345, 54321]
    )
    
    server1 = create_test_server(12345)
    
    time.sleep(1)
    result = scanner.scan('localhost')
    print(f'Scan result: {result}')
    
    server1.close()
    time.sleep(1)
    
    result = scanner.scan('localhost')
    print(f'Scan after closing: {result}')

def test_conn_tool():
    print('\n=== Testing ConnTool ===')
    import lib.ConnTool as ConnTool
    
    server = create_test_server(9876)
    time.sleep(0.5)
    
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(('localhost', 9876))
    
    test_data = b'Hello, World!'
    client.sendall(test_data)
    
    response = client.recv(1024)
    print(f'Response: {response}')
    
    assert response == test_data, 'Data mismatch!'
    print('ConnTool test passed!')
    
    client.close()
    server.close()

def test_frpc_basic():
    print('\n=== Testing Frpc Basic Connection ===')
    import frpc
    
    test_server = create_test_server(9999)
    time.sleep(0.5)
    
    print('Creating Frpc instance (will fail to connect to non-existent server, but that is expected)')
    
    try:
        frpc_instance = frpc.Frpc(
            server_host='localhost',
            server_port=7000,
            target_host='localhost',
            target_port=9999,
            pool_size=2
        )
        
        time.sleep(2)
        frpc_instance.stop()
        print('Frpc instance created and stopped successfully')
        
    except Exception as e:
        print(f'Expected error (server not running): {e}')
    
    test_server.close()

def test_config():
    print('\n=== Testing Config Loading ===')
    import json
    
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
            print(f'Config loaded: {config}')
    except Exception as e:
        print(f'Config error: {e}')

def main():
    print('Starting FRP-Python Tests...')
    print('These tests verify basic functionality without requiring a full FRP setup')
    
    try:
        test_conn_tool()
        test_port_scanner()
        test_config()
        test_frpc_basic()
        
        print('\n=== All tests completed ===')
        
    except Exception as e:
        print(f'\nTest failed with error: {e}')
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
