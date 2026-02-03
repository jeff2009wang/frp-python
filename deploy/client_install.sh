#!/bin/bash
###############################################################################
# FRP客户端一键安装脚本
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
SERVER_HOST=${2:-8.162.10.216}
SERVER_PORT=${3:-4433}

echo ""
echo "========================================"
echo "  FRP客户端一键安装"
echo "========================================"
echo ""
log_info "协议: $PROTOCOL"
log_info "服务端: ${SERVER_HOST}:${SERVER_PORT}"
echo ""

# 更新系统并安装依赖
log_step "更新系统并安装依赖..."
apt-get update -qq || yum update -y -q
apt-get install -y -qq curl wget python3 python3-pip openssl systemd || \
yum install -y -q curl wget python3 python3-pip openssl systemd

# 安装Hysteria2客户端
if [ "$PROTOCOL" = "hysteria2" ]; then
    log_step "安装Hysteria2客户端..."
    
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
    
    # 生成客户端配置
    log_step "生成客户端配置..."
    
    # 提示用户输入密码
    echo ""
    echo "请输入服务端配置的认证密码:"
    read -s -p "密码: " SERVER_PASSWORD
    echo ""
    
    if [ -z "$SERVER_PASSWORD" ]; then
        log_error "密码不能为空"
        exit 1
    fi
    
    mkdir -p /etc/hysteria2
    
    cat > /etc/hysteria2/client.yaml << EOF
server: ${SERVER_HOST}:${SERVER_PORT}

auth:
  type: password
  password: ${SERVER_PASSWORD}

socks5:
  listen: 127.0.0.1:1080

fastOpen: true
lazy: true

log:
  level: info
EOF
    
    log_info "客户端配置生成完成"
    
    # 创建systemd服务
    log_step "创建systemd服务..."
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
    
    # 启动服务
    log_step "启动Hysteria2客户端..."
    systemctl stop hysteria2-client 2>/dev/null || true
    systemctl start hysteria2-client
    
    sleep 2
    
    if systemctl is-active --quiet hysteria2-client; then
        log_info "✓ Hysteria2客户端启动成功"
    else
        log_error "✗ Hysteria2客户端启动失败"
        journalctl -u hysteria2-client -n 20 --no-pager
        exit 1
    fi
    
    # 测试连接
    log_step "测试SOCKS5代理..."
    sleep 3
    if curl -x socks5://127.0.0.1:1080 http://www.baidu.com -I -s --connect-timeout 5 | grep -q "HTTP"; then
        log_info "✓ SOCKS5代理测试成功"
    else
        log_warn "SOCKS5代理测试失败，请检查服务端配置"
    fi
    
    # 显示重要信息
    echo ""
    echo "========================================"
    echo "安装完成！"
    echo "========================================"
    echo ""
    echo "SOCKS5代理地址: 127.0.0.1:1080"
    echo "服务端地址: ${SERVER_HOST}:${SERVER_PORT}"
    echo ""
    echo "管理命令:"
    echo "  启动: systemctl start hysteria2-client"
    echo "  停止: systemctl stop hysteria2-client"
    echo "  重启: systemctl restart hysteria2-client"
    echo "  状态: systemctl status hysteria2-client"
    echo "  日志: journalctl -u hysteria2-client -f"
    echo ""
    echo "客户端配置: /etc/hysteria2/client.yaml"
    echo ""
    echo "========================================"
    echo ""

# 安装Python QUIC客户端
elif [ "$PROTOCOL" = "quic" ]; then
    log_step "安装Python QUIC客户端..."
    
    # 下载Python代码
    log_step "下载Python QUIC代码..."
    mkdir -p /opt/frp-python
    cd /opt/frp-python
    
    curl -L -o frpc_quic.py https://raw.githubusercontent.com/jeff2009wang/frp-python/master/version_quic_pure_python/frpc_quic.py
    curl -L -o server_cert.pem https://raw.githubusercontent.com/jeff2009wang/frp-python/master/version_quic_pure_python/server_cert.pem
    curl -L -o server_key.pem https://raw.githubusercontent.com/jeff2009wang/frp-python/master/version_quic_pure_python/server_key.pem
    
    # 安装Python依赖
    pip3 install aioquic pyOpenSSL certifi
    
    log_info "Python QUIC客户端安装完成"
    
    # 创建systemd服务
    log_step "创建systemd服务..."
    cat > /etc/systemd/system/frp-quic-client.service << EOF
[Unit]
Description=FRP QUIC Client
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/frp-python
ExecStart=/usr/bin/python3 frpc_quic.py ${SERVER_HOST} ${SERVER_PORT}
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF
    
    systemctl daemon-reload
    systemctl enable frp-quic-client
    
    log_warn "Python QUIC客户端需要手动启动"
    log_info "请运行: systemctl start frp-quic-client"
fi

echo ""
log_info "部署完成！"
echo ""
