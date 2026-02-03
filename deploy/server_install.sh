#!/bin/bash
###############################################################################
# FRP服务端一键安装脚本（纯Python版本）
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
SERVER_PORT=${1:-4433}

echo ""
echo "========================================"
echo "  FRP服务端一键安装 (Python QUIC)"
echo "========================================"
echo ""
log_info "端口: $SERVER_PORT"
echo ""

# 更新系统并安装依赖
log_step "更新系统并安装依赖..."
apt-get update -qq || yum update -y -q
apt-get install -y -qq curl wget python3 python3-pip git systemd || \
yum install -y -q curl wget python3 python3-pip git systemd

# 安装Python依赖
log_step "安装Python依赖..."
pip3 install aioquic pyOpenSSL certifi --break-system-packages --upgrade

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

# 创建证书
log_step "生成SSL证书..."
mkdir -p /etc/frp-quic
cd /etc/frp-quic

if [ ! -f "server_cert.pem" ] || [ ! -f "server_key.pem" ]; then
    openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
        -keyout server_key.pem \
        -out server_cert.pem \
        -subj '/CN=FRP-QUIC-Server/O=FRP/C=US'
    log_info "证书生成完成"
else
    log_info "证书已存在，跳过生成"
fi

# 创建systemd服务
log_step "创建systemd服务..."
cat > /etc/systemd/system/frp-quic-server.service << 'EOF'
[Unit]
Description=FRP QUIC Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/frp-python/frp-python
ExecStart=/usr/bin/python3 version_quic_pure_python/frps_quic.py 4433
Restart=on-failure
RestartSec=5s
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable frp-quic-server

# 配置防火墙
log_step "配置防火墙..."
if command -v ufw &> /dev/null; then
    ufw allow ${SERVER_PORT}/udp
elif command -v firewall-cmd &> /dev/null; then
    firewall-cmd --permanent --add-port=${SERVER_PORT}/udp
    firewall-cmd --reload
fi

# 启动服务
log_step "启动FRP QUIC服务..."
systemctl stop frp-quic-server 2>/dev/null || true
systemctl start frp-quic-server

sleep 3

if systemctl is-active --quiet frp-quic-server; then
    log_info "✓ FRP QUIC服务启动成功"
else
    log_error "✗ FRP QUIC服务启动失败"
    journalctl -u frp-quic-server -n 20 --no-pager
    exit 1
fi

# 显示重要信息
echo ""
echo "========================================"
echo "安装完成！"
echo "========================================"
echo ""
echo "服务端端口: ${SERVER_PORT}"
echo "协议: QUIC (UDP)"
echo ""
echo "管理命令:"
echo "  启动: systemctl start frp-quic-server"
echo "  停止: systemctl stop frp-quic-server"
echo "  重启: systemctl restart frp-quic-server"
echo "  状态: systemctl status frp-quic-server"
echo "  日志: journalctl -u frp-quic-server -f"
echo ""
echo "========================================"
echo ""

log_info "部署完成！"
echo ""
