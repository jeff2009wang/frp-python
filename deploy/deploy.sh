#!/bin/bash
###############################################################################
# FRP服务一键部署脚本 - Bash版本
# 支持 Hysteria2 和 Python QUIC
###############################################################################

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 配置变量
CLIENT_HOST="47.117.159.145"
CLIENT_PORT="9321"
CLIENT_USER="root"
CLIENT_PASS="uUyb-ARfcT=D2mMpBn(L"

SERVER_HOST="8.162.10.216"
SERVER_PORT="22"
SERVER_USER="root"
SERVER_PASS="JeiFing1234@"

PROTOCOL="hysteria2"
SERVER_PORT_NUM="4433"

# 日志函数
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# SSH命令封装
ssh_exec() {
    local host=$1
    local port=$2
    local user=$3
    local pass=$4
    local cmd=$5

    sshpass -p "$pass" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p "$port" "${user}@${host}" "$cmd"
}

scp_file() {
    local host=$1
    local port=$2
    local user=$3
    local pass=$4
    local src=$5
    local dst=$6

    sshpass -p "$pass" scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -P "$port" "$src" "${user}@${host}:${dst}"
}

# 测试连接
test_connection() {
    log_step "测试服务器连接..."

    if ssh_exec "$CLIENT_HOST" "$CLIENT_PORT" "$CLIENT_USER" "$CLIENT_PASS" "echo 'client_ok'" | grep -q "client_ok"; then
        log_info "✓ 客户端服务器连接成功"
    else
        log_error "✗ 客户端服务器连接失败"
        return 1
    fi

    if ssh_exec "$SERVER_HOST" "$SERVER_PORT" "$SERVER_USER" "$SERVER_PASS" "echo 'server_ok'" | grep -q "server_ok"; then
        log_info "✓ 服务端服务器连接成功"
    else
        log_error "✗ 服务端服务器连接失败"
        return 1
    fi
}

# 准备环境
prepare_environment() {
    local host=$1
    local port=$2
    local user=$3
    local pass=$4
    local server_type=$5

    log_step "准备${server_type}运行环境..."

    ssh_exec "$host" "$port" "$user" "$pass" "
        apt-get update -qq || yum update -y -q
        apt-get install -y -qq curl wget python3 python3-pip openssl systemd || yum install -y -q curl wget python3 python3-pip openssl systemd
        mkdir -p /opt/frp-service
    "

    log_info "${server_type}环境准备完成"
}

# 安装Hysteria2服务端
install_hysteria2_server() {
    log_step "安装Hysteria2服务端..."

    # 下载Hysteria2
    ssh_exec "$SERVER_HOST" "$SERVER_PORT" "$SERVER_USER" "$SERVER_PASS" "
        ARCH=\$(uname -m)
        case \$ARCH in
            x86_64) BINARY='hysteria2-linux-amd64' ;;
            aarch64|arm64) BINARY='hysteria2-linux-arm64' ;;
            armv7l) BINARY='hysteria2-linux-armv7' ;;
            *) echo 'Unsupported architecture'; exit 1 ;;
        esac

        curl -L -o /usr/local/bin/hysteria2 https://github.com/apernet/hysteria2/releases/latest/download/\$BINARY
        chmod +x /usr/local/bin/hysteria2
    "

    # 生成证书和配置
    ssh_exec "$SERVER_HOST" "$SERVER_PORT" "$SERVER_USER" "$SERVER_PASS" "
        mkdir -p /etc/hysteria2

        # 生成自签名证书
        openssl req -x509 -newkey rsa:2048 -nodes -days 365 \\
            -keyout /etc/hysteria2/key.pem \\
            -out /etc/hysteria2/cert.pem \\
            -subj '/CN=Hysteria2-Server/O=Hysteria2/C=US'

        # 生成密码
        PASSWORD=\$(openssl rand -base64 16)

        # 生成配置文件
        cat > /etc/hysteria2/config.yaml << EOF
listen: :${SERVER_PORT_NUM}

tls:
  cert: /etc/hysteria2/cert.pem
  key: /etc/hysteria2/key.pem

auth:
  type: password
  password: \${PASSWORD}

bandwidth:
  up: 1 gbps
  down: 1 gbps

quic:
  initStreamReceiveWindow: 8388608
  maxStreamReceiveWindow: 8388608
  initConnReceiveWindow: 20971520
  maxConnReceiveWindow: 20971520
  maxIdleTimeout: 30s
  keepAlivePeriod: 10s

fastOpen: true
lazy: true

log:
  level: info
EOF

        echo 'Hysteria2密码: '\${PASSWORD}
    "

    # 创建systemd服务
    ssh_exec "$SERVER_HOST" "$SERVER_PORT" "$SERVER_USER" "$SERVER_PASS" "
        cat > /etc/systemd/system/hysteria2-server.service << 'EOF'
[Unit]
Description=Hysteria2 Server Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/hysteria2 server -c /etc/hysteria2/config.yaml
Restart=on-failure
RestartSec=5s
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF

        systemctl daemon-reload
        systemctl enable hysteria2-server
    "

    log_info "Hysteria2服务端安装完成"
}

# 安装Hysteria2客户端
install_hysteria2_client() {
    log_step "安装Hysteria2客户端..."

    # 下载Hysteria2
    ssh_exec "$CLIENT_HOST" "$CLIENT_PORT" "$CLIENT_USER" "$CLIENT_PASS" "
        ARCH=\$(uname -m)
        case \$ARCH in
            x86_64) BINARY='hysteria2-linux-amd64' ;;
            aarch64|arm64) BINARY='hysteria2-linux-arm64' ;;
            armv7l) BINARY='hysteria2-linux-armv7' ;;
            *) echo 'Unsupported architecture'; exit 1 ;;
        esac

        curl -L -o /usr/local/bin/hysteria2 https://github.com/apernet/hysteria2/releases/latest/download/\$BINARY
        chmod +x /usr/local/bin/hysteria2
    "

    # 获取服务端密码
    HY2_PASSWORD=$(ssh_exec "$SERVER_HOST" "$SERVER_PORT" "$SERVER_USER" "$SERVER_PASS" "
        grep 'password:' /etc/hysteria2/config.yaml | awk '{print \$2}'
    " | tr -d '\r')

    # 生成客户端配置
    ssh_exec "$CLIENT_HOST" "$CLIENT_PORT" "$CLIENT_USER" "$CLIENT_PASS" "
        mkdir -p /etc/hysteria2

        cat > /etc/hysteria2/client.yaml << EOF
server: ${SERVER_HOST}:${SERVER_PORT_NUM}

auth:
  type: password
  password: ${HY2_PASSWORD}

socks5:
  listen: 127.0.0.1:1080

fastOpen: true
lazy: true

log:
  level: info
EOF
    "

    # 创建systemd服务
    ssh_exec "$CLIENT_HOST" "$CLIENT_PORT" "$CLIENT_USER" "$CLIENT_PASS" "
        cat > /etc/systemd/system/hysteria2-client.service << 'EOF'
[Unit]
Description=Hysteria2 Client Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/hysteria2 client -c /etc/hysteria2/client.yaml
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

        systemctl daemon-reload
        systemctl enable hysteria2-client
    "

    log_info "Hysteria2客户端安装完成"
}

# 安装Python QUIC服务端
install_quic_server() {
    log_step "安装Python QUIC服务端..."

    ssh_exec "$SERVER_HOST" "$SERVER_PORT" "$SERVER_USER" "$SERVER_PASS" "
        # 安装Python依赖
        pip3 install aioquic pyOpenSSL certifi

        # 创建项目目录
        mkdir -p /opt/frp-quic
        cd /opt/frp-quic

        # 生成证书
        openssl req -x509 -newkey rsa:2048 -nodes -days 365 \\
            -keyout server_key.pem \\
            -out server_cert.pem \\
            -subj '/CN=FRP-QUIC-Server'

        # 创建systemd服务
        cat > /etc/systemd/system/frp-quic.service << 'EOF'
[Unit]
Description=FRP QUIC Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/frp-quic
ExecStart=/usr/bin/python3 -c \"
import asyncio
import logging
from aioquic.quic.configuration import QuicConfiguration
from aioquic.asyncio import serve
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('frps-quic')

async def handle_stream(stream_id):
    logger.info(f'New stream: {stream_id}')

async def main():
    config = QuicConfiguration(is_client=False, alpn_protocols=['frp-quic'])
    config.load_cert_chain(Path('server_cert.pem'), Path('server_key.pem'))
    await serve('0.0.0.0', ${SERVER_PORT_NUM}, configuration=config, stream_handler=handle_stream)
    logger.info(f'Server listening on port ${SERVER_PORT_NUM}')
    await asyncio.Future()

asyncio.run(main())
\"
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

        systemctl daemon-reload
        systemctl enable frp-quic
    "

    log_info "Python QUIC服务端安装完成"
}

# 配置防火墙
configure_firewall() {
    local host=$1
    local port=$2
    local user=$3
    local pass=$4

    log_step "配置防火墙..."

    ssh_exec "$host" "$port" "$user" "$pass" "
        if command -v ufw &> /dev/null; then
            ufw allow ${SERVER_PORT_NUM}/tcp
            ufw allow ${SERVER_PORT_NUM}/udp
        elif command -v firewall-cmd &> /dev/null; then
            firewall-cmd --permanent --add-port=${SERVER_PORT_NUM}/tcp
            firewall-cmd --permanent --add-port=${SERVER_PORT_NUM}/udp
            firewall-cmd --reload
        fi
    "

    log_info "防火墙配置完成"
}

# 启动服务
start_services() {
    log_step "启动服务..."

    if [ "$PROTOCOL" = "hysteria2" ]; then
        ssh_exec "$SERVER_HOST" "$SERVER_PORT" "$SERVER_USER" "$SERVER_PASS" "
            systemctl stop hysteria2-server 2>/dev/null || true
            systemctl start hysteria2-server
            sleep 2
            systemctl status hysteria2-server --no-pager
        "

        ssh_exec "$CLIENT_HOST" "$CLIENT_PORT" "$CLIENT_USER" "$CLIENT_PASS" "
            systemctl stop hysteria2-client 2>/dev/null || true
            systemctl start hysteria2-client
            sleep 2
            systemctl status hysteria2-client --no-pager
        "
    elif [ "$PROTOCOL" = "quic" ]; then
        ssh_exec "$SERVER_HOST" "$SERVER_PORT" "$SERVER_USER" "$SERVER_PASS" "
            systemctl stop frp-quic 2>/dev/null || true
            systemctl start frp-quic
            sleep 2
            systemctl status frp-quic --no-pager
        "
    fi

    log_info "服务启动完成"
}

# 验证部署
verify_deployment() {
    log_step "验证部署..."

    echo ""
    echo "========================================"
    echo "部署验证报告"
    echo "========================================"

    if [ "$PROTOCOL" = "hysteria2" ]; then
        # 检查服务端
        echo ""
        echo "服务端状态:"
        ssh_exec "$SERVER_HOST" "$SERVER_PORT" "$SERVER_USER" "$SERVER_PASS" "
            systemctl is-active hysteria2-server && echo '  ✓ 运行中' || echo '  ✗ 未运行'
            ss -tuln | grep ${SERVER_PORT_NUM} && echo '  ✓ 端口监听正常' || echo '  ✗ 端口未监听'
        "

        # 检查客户端
        echo ""
        echo "客户端状态:"
        ssh_exec "$CLIENT_HOST" "$CLIENT_PORT" "$CLIENT_USER" "$CLIENT_PASS" "
            systemctl is-active hysteria2-client && echo '  ✓ 运行中' || echo '  ✗ 未运行'
            ss -tuln | grep 1080 && echo '  ✓ SOCKS5端口监听正常' || echo '  ✗ SOCKS5端口未监听'
        "

        # 测试SOCKS5代理
        echo ""
        echo "测试SOCKS5代理:"
        if ssh_exec "$CLIENT_HOST" "$CLIENT_PORT" "$CLIENT_USER" "$CLIENT_PASS" "curl -x socks5://127.0.0.1:1080 http://www.baidu.com -I -s --connect-timeout 5" | grep -q "HTTP"; then
            echo "  ✓ SOCKS5代理工作正常"
        else
            echo "  ✗ SOCKS5代理测试失败"
        fi

        echo ""
        echo "========================================"
        echo "客户端SOCKS5代理地址: ${CLIENT_HOST}:1080"
        echo "========================================"

    elif [ "$PROTOCOL" = "quic" ]; then
        echo ""
        echo "服务端状态:"
        ssh_exec "$SERVER_HOST" "$SERVER_PORT" "$SERVER_USER" "$SERVER_PASS" "
            systemctl is-active frp-quic && echo '  ✓ 运行中' || echo '  ✗ 未运行'
            ss -tuln | grep ${SERVER_PORT_NUM} && echo '  ✓ 端口监听正常' || echo '  ✗ 端口未监听'
        "
        echo ""
        echo "========================================"
        echo "注意: Python QUIC需要客户端连接"
        echo "服务端地址: ${SERVER_HOST}:${SERVER_PORT_NUM}"
        echo "========================================"
    fi

    echo ""
}

# 主部署流程
main() {
    echo ""
    echo "========================================"
    echo "  FRP服务一键部署脚本"
    echo "========================================"
    echo ""

    # 检查sshpass
    if ! command -v sshpass &> /dev/null; then
        log_warn "sshpass未安装，正在安装..."
        if [[ "$OSTYPE" == "darwin"* ]]; then
            brew install sshpass
        else
            sudo apt-get install -y sshpass || sudo yum install -y sshpass
        fi
    fi

    # 测试连接
    if ! test_connection; then
        log_error "服务器连接测试失败，部署终止"
        exit 1
    fi

    echo ""

    # 准备环境
    prepare_environment "$CLIENT_HOST" "$CLIENT_PORT" "$CLIENT_USER" "$CLIENT_PASS" "客户端"
    prepare_environment "$SERVER_HOST" "$SERVER_PORT" "$SERVER_USER" "$SERVER_PASS" "服务端"

    echo ""

    # 安装服务
    if [ "$PROTOCOL" = "hysteria2" ]; then
        install_hysteria2_server
        install_hysteria2_client
        configure_firewall "$SERVER_HOST" "$SERVER_PORT" "$SERVER_USER" "$SERVER_PASS"
    elif [ "$PROTOCOL" = "quic" ]; then
        install_quic_server
        configure_firewall "$SERVER_HOST" "$SERVER_PORT" "$SERVER_USER" "$SERVER_PASS"
    fi

    echo ""

    # 启动服务
    start_services

    echo ""

    # 验证部署
    verify_deployment

    echo ""
    log_info "部署完成！"
    echo ""
}

# 运行主函数
main
