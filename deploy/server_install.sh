#!/bin/bash
###############################################################################
# FRP服务端一键安装脚本
# 从GitHub自动下载并部署
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
PROTOCOL=${1:-hysteria2}
SERVER_PORT=${2:-4433}

echo ""
echo "========================================"
echo "  FRP服务端一键安装"
echo "========================================"
echo ""
log_info "协议: $PROTOCOL"
log_info "端口: $SERVER_PORT"
echo ""

# 更新系统并安装依赖
log_step "更新系统并安装依赖..."
apt-get update -qq || yum update -y -q
apt-get install -y -qq curl wget python3 python3-pip openssl systemd || \
yum install -y -q curl wget python3 python3-pip openssl systemd

# 安装Hysteria2
if [ "$PROTOCOL" = "hysteria2" ]; then
    log_step "安装Hysteria2..."
    
    # 下载Hysteria2
    ARCH=$(uname -m)
    case $ARCH in
        x86_64) BINARY='hysteria2-linux-amd64' ;;
        aarch64|arm64) BINARY='hysteria2-linux-arm64' ;;
        armv7l) BINARY='hysteria2-linux-armv7' ;;
        *) 
            log_error "不支持的架构: $ARCH"
            exit 1
            ;;
    esac
    
    log_info "正在下载 Hysteria2 for $ARCH..."
    
    if ! curl -L -o /usr/local/bin/hysteria2 "https://github.com/apernet/hysteria2/releases/latest/download/$BINARY"; then
        log_error "Hysteria2 下载失败，尝试使用备用下载地址..."
        # 备用下载地址：指定版本
        curl -L -o /usr/local/bin/hysteria2 "https://github.com/apernet/hysteria2/releases/download/v2.4.4/$BINARY" || {
            log_error "Hysteria2 下载失败，请检查网络连接"
            exit 1
        }
    fi
    
    chmod +x /usr/local/bin/hysteria2
    
    # 验证文件是否下载成功
    if [ ! -s /usr/local/bin/hysteria2 ]; then
        log_error "Hysteria2 文件下载失败或为空"
        exit 1
    fi
    
    log_info "Hysteria2下载完成"
    
    # 生成证书和配置
    log_step "生成证书和配置..."
    mkdir -p /etc/hysteria2
    
    openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
        -keyout /etc/hysteria2/key.pem \
        -out /etc/hysteria2/cert.pem \
        -subj '/CN=Hysteria2-Server/O=Hysteria2/C=US'
    
    PASSWORD=$(openssl rand -base64 16)
    
    cat > /etc/hysteria2/config.yaml << EOF
listen: :${SERVER_PORT}

tls:
  cert: /etc/hysteria2/cert.pem
  key: /etc/hysteria2/key.pem

auth:
  type: password
  password: ${PASSWORD}

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
    
    log_info "配置文件生成完成"
    
    # 创建systemd服务
    log_step "创建systemd服务..."
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
    
    # 配置防火墙
    log_step "配置防火墙..."
    if command -v ufw &> /dev/null; then
        ufw allow ${SERVER_PORT}/tcp
        ufw allow ${SERVER_PORT}/udp
    elif command -v firewall-cmd &> /dev/null; then
        firewall-cmd --permanent --add-port=${SERVER_PORT}/tcp
        firewall-cmd --permanent --add-port=${SERVER_PORT}/udp
        firewall-cmd --reload
    fi
    
    # 启动服务
    log_step "启动Hysteria2服务..."
    systemctl stop hysteria2-server 2>/dev/null || true
    systemctl start hysteria2-server
    
    sleep 2
    
    if systemctl is-active --quiet hysteria2-server; then
        log_info "✓ Hysteria2服务启动成功"
    else
        log_error "✗ Hysteria2服务启动失败"
        journalctl -u hysteria2-server -n 20 --no-pager
        exit 1
    fi
    
    # 保存密码到文件（方便客户端获取）
    echo "${PASSWORD}" > /tmp/hysteria2_password.txt
    chmod 600 /tmp/hysteria2_password.txt
    
    # 显示重要信息
    echo ""
    echo "========================================"
    echo "安装完成！"
    echo "========================================"
    echo ""
    echo "服务端端口: ${SERVER_PORT}"
    echo "认证密码: ${PASSWORD}"
    echo ""
    echo "⚠️  请务必保存此密码，客户端连接时需要使用！"
    echo ""
    echo "密码已保存到: /tmp/hysteria2_password.txt"
    echo ""
    echo "管理命令:"
    echo "  启动: systemctl start hysteria2-server"
    echo "  停止: systemctl stop hysteria2-server"
    echo "  重启: systemctl restart hysteria2-server"
    echo "  状态: systemctl status hysteria2-server"
    echo "  日志: journalctl -u hysteria2-server -f"
    echo "  查看密码: cat /tmp/hysteria2_password.txt"
    echo ""
    echo "========================================"
    echo ""

# 安装Python QUIC
elif [ "$PROTOCOL" = "quic" ]; then
    log_step "安装Python QUIC..."
    
    # 安装Python依赖
    pip3 install aioquic pyOpenSSL certifi
    
    log_info "Python QUIC安装完成"
    
    log_warn "Python QUIC需要手动启动服务"
    log_info "请运行: python3 /opt/frp-python/frps_quic.py ${SERVER_PORT}"
fi

echo ""
log_info "部署完成！"
echo ""
