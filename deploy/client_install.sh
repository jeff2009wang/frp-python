#!/bin/bash
###############################################################################
# FRP客户端一键安装脚本（纯Python版本）
# 使用Python QUIC，无需下载额外二进制文件
###############################################################################

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# 获取参数
SERVER_HOST=${1:-127.0.0.1}
SERVER_PORT=${2:-4433}

if [ -z "$SERVER_HOST" ] || [ "$SERVER_HOST" = "-h" ] || [ "$SERVER_HOST" = "--help" ]; then
    echo "用法: $0 <服务端IP> [服务端端口]"
    echo ""
    echo "示例:"
    echo "  $0 123.45.67.89         # 使用默认端口 4433"
    echo "  $0 123.45.67.89 8443    # 使用自定义端口 8443"
    exit 1
fi

echo ""
echo "========================================"
echo "  FRP客户端一键安装 (Python QUIC)"
echo "========================================"
echo ""
log_info "服务端: ${SERVER_HOST}:${SERVER_PORT}"
echo ""

# 更新系统并安装依赖
log_step "更新系统并安装依赖..."
apt-get update -qq || yum update -y -q
apt-get install -y -qq curl wget python3 python3-pip git systemd || \
yum install -y -q curl wget python3 python3-pip git systemd

# 安装Python依赖
log_step "安装Python依赖..."
pip3 install aioquic pyOpenSSL certifi --upgrade

# 下载代码
log_step "下载FRP代码..."
mkdir -p /opt/frp-python
cd /opt/frp-python

if [ -d "frp-python" ]; then
    cd frp-python
    git pull
else
    git clone https://github.com/jeff2009wang/frp-python.git
    cd frp-python
fi

# 创建systemd服务
log_step "创建systemd服务..."
cat > /etc/systemd/system/frp-quic-client.service << EOF
[Unit]
Description=FRP QUIC Client
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/frp-python/frp-python
ExecStart=/usr/bin/python3 version_quic_pure_python/frpc_quic.py ${SERVER_HOST} ${SERVER_PORT}
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable frp-quic-client

# 启动服务
log_step "启动FRP QUIC客户端..."
systemctl stop frp-quic-client 2>/dev/null || true
systemctl start frp-quic-client

sleep 3

if systemctl is-active --quiet frp-quic-client; then
    log_info "✓ FRP QUIC客户端启动成功"
else
    log_error "✗ FRP QUIC客户端启动失败"
    journalctl -u frp-quic-client -n 20 --no-pager
    exit 1
fi

# 显示重要信息
echo ""
echo "========================================"
echo "安装完成！"
echo "========================================"
echo ""
echo "服务端地址: ${SERVER_HOST}:${SERVER_PORT}"
echo "协议: QUIC (UDP)"
echo ""
echo "管理命令:"
echo "  启动: systemctl start frp-quic-client"
echo "  停止: systemctl stop frp-quic-client"
echo "  重启: systemctl restart frp-quic-client"
echo "  状态: systemctl status frp-quic-client"
echo "  日志: journalctl -u frp-quic-client -f"
echo ""
echo "使用方法:"
echo "  在本地启动服务后，会自动通过服务端暴露出去"
echo "  例如：本地启动 SSH (端口 22)，可通过 服务端IP:22 访问"
echo ""
echo "========================================"
echo ""

log_info "部署完成！"
echo ""
