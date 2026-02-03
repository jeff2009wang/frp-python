#!/bin/bash
###############################################################################
# Hysteria2 服务端安装脚本
# 支持 Ubuntu/Debian/CentOS/Alpine
###############################################################################

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 配置变量
INSTALL_DIR="/usr/local/bin"
CONFIG_DIR="/etc/hysteria2"
SERVICE_NAME="hysteria2-server"
PORT=4433
DOMAIN=""  # 留空则使用自签名证书
EMAIL=""

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检测系统类型
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
    else
        log_error "无法检测操作系统类型"
        exit 1
    fi
    
    log_info "检测到操作系统: $OS $OS_VERSION"
}

# 安装依赖
install_dependencies() {
    log_info "安装依赖包..."
    
    case $OS in
        ubuntu|debian)
            apt-get update -qq
            apt-get install -y -qq curl wget openssl systemd
            ;;
        centos|rhel|fedora)
            yum install -y -q curl wget openssl systemd
            ;;
        alpine)
            apk add --no-cache curl wget openssl
            ;;
        *)
            log_error "不支持的操作系统: $OS"
            exit 1
            ;;
    esac
}

# 下载Hysteria2
download_hysteria2() {
    log_info "下载Hysteria2二进制文件..."
    
    ARCH=$(uname -m)
    case $ARCH in
        x86_64)
            BINARY_NAME="hysteria2-linux-amd64"
            ;;
        aarch64|arm64)
            BINARY_NAME="hysteria2-linux-arm64"
            ;;
        armv7l)
            BINARY_NAME="hysteria2-linux-armv7"
            ;;
        *)
            log_error "不支持的架构: $ARCH"
            exit 1
            ;;
    esac
    
    DOWNLOAD_URL="https://github.com/apernet/hysteria2/releases/latest/download/${BINARY_NAME}"
    
    # 备份旧版本
    if [ -f "$INSTALL_DIR/hysteria2" ]; then
        cp "$INSTALL_DIR/hysteria2" "$INSTALL_DIR/hysteria2.bak"
        log_info "已备份旧版本"
    fi
    
    # 下载新版本
    if curl -L -o "$INSTALL_DIR/hysteria2" "$DOWNLOAD_URL"; then
        chmod +x "$INSTALL_DIR/hysteria2"
        log_info "✓ Hysteria2下载成功"
    else
        log_error "✗ Hysteria2下载失败"
        # 恢复备份
        if [ -f "$INSTALL_DIR/hysteria2.bak" ]; then
            mv "$INSTALL_DIR/hysteria2.bak" "$INSTALL_DIR/hysteria2"
            log_info "已恢复旧版本"
        fi
        exit 1
    fi
    
    # 清理备份
    rm -f "$INSTALL_DIR/hysteria2.bak"
}

# 生成证书
generate_certificate() {
    log_info "配置SSL证书..."
    
    mkdir -p "$CONFIG_DIR"
    
    if [ -n "$DOMAIN" ]; then
        # 使用ACME获取证书
        log_info "使用域名获取证书: $DOMAIN"
        
        # 安装acme.sh
        if [ ! -f ~/.acme.sh/acme.sh ]; then
            curl https://get.acme.sh | sh
        fi
        
        # 获取证书
        ~/.acme.sh/acme.sh --issue -d "$DOMAIN" --standalone
        ~/.acme.sh/acme.sh --install-cert -d "$DOMAIN" \
            --cert-file "$CONFIG_DIR/cert.pem" \
            --key-file "$CONFIG_DIR/key.pem" \
            --fullchain-file "$CONFIG_DIR/fullchain.pem"
    else
        # 使用自签名证书
        log_info "生成自签名证书..."
        
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout "$CONFIG_DIR/key.pem" \
            -out "$CONFIG_DIR/cert.pem" \
            -subj "/CN=Hysteria2-Server/O=Hysteria2/C=US"
        
        log_info "✓ 自签名证书生成完成"
        log_warn "注意: 自签名证书需要在客户端开启 skip-cert-verify"
    fi
}

# 生成配置文件
generate_config() {
    log_info "生成配置文件..."
    
    PASSWORD=$(openssl rand -base64 16)
    
    cat > "$CONFIG_DIR/config.yaml" << EOF
# Hysteria2 服务端配置
listen: :$PORT

tls:
  cert: $CONFIG_DIR/cert.pem
  key: $CONFIG_DIR/key.pem

auth:
  type: password
  password: $PASSWORD

# 带宽配置（根据实际情况调整）
bandwidth:
  up: 1 gbps  # 上行带宽
  down: 1 gbps  # 下行带宽

# 禁用流量混淆（可选）
obfs: null

# QUIC参数优化
quic:
  initStreamReceiveWindow: 8388608
  maxStreamReceiveWindow: 8388608
  initConnReceiveWindow: 20971520
  maxConnReceiveWindow: 20971520
  maxIdleTimeout: 30s
  keepAlivePeriod: 10s

# 快速连接
fastOpen: true
lazy: true

# 日志配置
log:
  level: info
EOF
    
    log_info "✓ 配置文件生成完成: $CONFIG_DIR/config.yaml"
    
    # 显示密码
    echo ""
    echo "========================================"
    echo "重要信息请保存"
    echo "========================================"
    echo "服务端端口: $PORT"
    echo "认证密码: $PASSWORD"
    echo "证书路径: $CONFIG_DIR/cert.pem"
    echo "========================================"
    echo ""
}

# 创建systemd服务
create_systemd_service() {
    log_info "创建systemd服务..."
    
    cat > "/etc/systemd/system/$SERVICE_NAME.service" << EOF
[Unit]
Description=Hysteria2 Server Service
After=network.target

[Service]
Type=simple
ExecStart=$INSTALL_DIR/hysteria2 server -c $CONFIG_DIR/config.yaml
Restart=on-failure
RestartSec=5s
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF
    
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    
    log_info "✓ systemd服务创建完成"
}

# 配置防火墙
configure_firewall() {
    log_info "配置防火墙..."
    
    if command -v ufw &> /dev/null; then
        ufw allow $PORT/tcp
        ufw allow $PORT/udp
        log_info "✓ UFW防火墙规则已添加"
    elif command -v firewall-cmd &> /dev/null; then
        firewall-cmd --permanent --add-port=$PORT/tcp
        firewall-cmd --permanent --add-port=$PORT/udp
        firewall-cmd --reload
        log_info "✓ firewalld防火墙规则已添加"
    else
        log_warn "未检测到防火墙，请手动开放端口 $PORT"
    fi
}

# 启动服务
start_service() {
    log_info "启动Hysteria2服务..."
    
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl start "$SERVICE_NAME"
    
    sleep 2
    
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_info "✓ Hysteria2服务启动成功"
        systemctl status "$SERVICE_NAME" --no-pager
    else
        log_error "✗ Hysteria2服务启动失败"
        journalctl -u "$SERVICE_NAME" -n 20 --no-pager
        exit 1
    fi
}

# 显示服务信息
show_info() {
    log_info "安装完成！"
    echo ""
    echo "========================================"
    echo "服务信息"
    echo "========================================"
    echo "服务名称: $SERVICE_NAME"
    echo "监听端口: $PORT"
    echo "配置目录: $CONFIG_DIR"
    echo "二进制文件: $INSTALL_DIR/hysteria2"
    echo ""
    echo "常用命令:"
    echo "  启动服务: systemctl start $SERVICE_NAME"
    echo "  停止服务: systemctl stop $SERVICE_NAME"
    echo "  重启服务: systemctl restart $SERVICE_NAME"
    echo "  查看状态: systemctl status $SERVICE_NAME"
    echo "  查看日志: journalctl -u $SERVICE_NAME -f"
    echo "========================================"
}

# 主函数
main() {
    echo ""
    echo "========================================"
    echo "  Hysteria2 服务端安装脚本"
    echo "========================================"
    echo ""
    
    # 检查root权限
    if [ "$EUID" -ne 0 ]; then
        log_error "请使用root权限运行此脚本"
        exit 1
    fi
    
    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --port)
                PORT="$2"
                shift 2
                ;;
            --domain)
                DOMAIN="$2"
                shift 2
                ;;
            --email)
                EMAIL="$2"
                shift 2
                ;;
            *)
                log_error "未知参数: $1"
                exit 1
                ;;
        esac
    done
    
    # 执行安装步骤
    detect_os
    install_dependencies
    download_hysteria2
    generate_certificate
    generate_config
    create_systemd_service
    configure_firewall
    start_service
    show_info
}

# 运行主函数
main "$@"
