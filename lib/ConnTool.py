# -*- coding: utf-8 -*-

import sys
import socket
import logging
import threading
import os

PKT_BUFF_SIZE = 65536

logger = logging.getLogger("Proxy Logging")
formatter = logging.Formatter('%(name)-12s %(asctime)s %(levelname)-8s %(lineno)-4d %(message)s', '%Y %b %d %a %H:%M:%S')

stream_handler = logging.StreamHandler(sys.stderr)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)
logger.setLevel(logging.INFO)


def optimize_socket(sock):
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass
    
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except Exception:
        pass
    
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass
    
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
    except Exception:
        pass


def tcp_mapping_worker(conn_receiver, conn_sender):
    optimize_socket(conn_receiver)
    optimize_socket(conn_sender)
    
    logger.debug("start")
    try:
        while True:
            data = conn_receiver.recv(PKT_BUFF_SIZE)
            if not data:
                logger.debug('No more data is received.')
                break
            
            try:
                conn_sender.sendall(data)
            except Exception:
                logger.error('Failed sending data.')
                break
    except Exception as e:
        logger.debug(f'Connection error: {e}')
    finally:
        try:
            conn_receiver.close()
        except Exception:
            pass
        try:
            conn_sender.close()
        except Exception:
            pass


def join(connA, connB):
    optimize_socket(connA)
    optimize_socket(connB)
    
    t1 = threading.Thread(target=tcp_mapping_worker, args=(connA, connB), daemon=True)
    t2 = threading.Thread(target=tcp_mapping_worker, args=(connB, connA), daemon=True)
    
    t1.start()
    t2.start()
    
    return t1, t2


if __name__ == '__main__':
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('0.0.0.0', 8080))
    sock.listen(100)
    conn1, addr1 = sock.accept()

    sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock2.bind(('0.0.0.0', 7000))
    sock2.listen(100)

    server_conn = socket.create_connection(('localhost', 7000))

    conn2, addr2 = sock2.accept()
    join(conn1, conn2)

    target_conn = socket.create_connection(('192.168.1.101', 3389))
    join(server_conn, target_conn)
