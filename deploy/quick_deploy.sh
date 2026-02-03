#!/bin/bash
###############################################################################
# 一键部署脚本 - Hysteria2/Python QUIC
###############################################################################

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# 显示横幅
show_banner() {
    echo ""
    echo "========================================"
    echo "  FRP服务自动化部署工具"
    echo "  支持 Hysteria2 / Python QUIC"
    echo "========================================"
    echo ""
}

# 检查Python环境
check_python() {
    log_step "检查Python环境..."
    
    if ! command -v python3 &> /dev/null; then
        log_error "未找到Python3，请先安装Python 3.7+"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    log_info "Python版本: $PYTHON_VERSION"
}

# 安装依赖
install_dependencies() {
    log_step "安装Python依赖..."
    
    if ! python3 -c "import paramiko" 2>/dev/null; then
        log_info "安装paramiko..."
        pip3 install paramiko cryptography
    else
        log_info "paramiko已安装"
    fi
}

# 选择协议
select_protocol() {
    echo ""
    echo "请选择部署协议:"
    echo "  1) Hysteria2 (推荐，高性能)"
    echo "  2) Python QUIC (纯Python实现)"
    echo ""
    read -p "请输入选项 [1-2]: " protocol_choice
    
    case $protocol_choice in
        1)
            PROTOCOL="hysteria2"
            log_info "已选择: Hysteria2"
            ;;
        2)
            PROTOCOL="quic"
            log_info "已选择: Python QUIC"
            ;;
        *)
            log_error "无效选项"
            exit 1
            ;;
    esac
}

# 配置服务器
configure_servers() {
    log_step "配置服务器信息..."
    
    # 使用预配置的服务器信息
    log_info "使用预配置的服务器信息"
    log_info "客户端服务器: 47.117.159.145:9321"
    log_info "服务端服务器: 8.162.10.216:22"
    
    echo ""
    read -p "是否使用预配置信息? [Y/n]: " use_default
    
    if [[ "$use_default" =~ ^[Nn]$ ]]; then
        read -p "客户端服务器IP: " CLIENT_HOST
        read -p "客户端服务器端口: " CLIENT_PORT
        read -p "客户端服务器密码: " CLIENT_PASSWORD
        read -p "服务端服务器IP: " SERVER_HOST
        read -p "服务端服务器端口: " SERVER_PORT
        read -p "服务端服务器密码: " SERVER_PASSWORD
    fi
}

# 配置端口
configure_port() {
    echo ""
    
    if [ "$PROTOCOL" = "hysteria2" ]; then
        read -p "服务端端口 [默认: 4433]: " SERVER_PORT_INPUT
        SERVER_PORT=${SERVER_PORT_INPUT:-4433}
    else
        read -p "服务端端口 [默认: 7000]: " SERVER_PORT_INPUT
        SERVER_PORT=${SERVER_PORT_INPUT:-7000}
    fi
    
    log_info "服务端端口: $SERVER_PORT"
}

# 执行部署
deploy() {
    log_step "开始部署..."
    echo ""
    
    # 构建部署命令
    DEPLOY_CMD="python3 auto_deploy.py --protocol $PROTOCOL --server-port $SERVER_PORT"
    
    # 执行部署
    if $DEPLOY_CMD; then
        echo ""
        log_info "部署完成！"
        return 0
    else
        echo ""
        log_error "部署失败"
        return 1
    fi
}

# 执行验证
verify() {
    log_step "验证部署..."
    echo ""
    
    # 执行验证
    if python3 verify_deployment.py --protocol $PROTOCOL; then
        echo ""
        log_info "验证通过！"
        return 0
    else
        echo ""
        log_warn "验证发现问题，请检查日志"
        return 1
    fi
}

# 显示后续步骤
show_next_steps() {
    echo ""
    echo "========================================"
    echo "  部署完成"
    echo "========================================"
    echo ""
    echo "后续步骤:"
    echo ""
    echo "1. 查看服务状态:"
    if [ "$PROTOCOL" = "hysteria2" ]; then
        echo "   客户端: ssh -p 9321 root@47.117.159.145 'systemctl status hysteria2-client'"
        echo "   服务端: ssh -p 22 root@8.162.10.216 'systemctl status hysteria2-server'"
    else
        echo "   服务端: ssh -p 22 root@8.162.10.216 'systemctl status frp-quic'"
    fi
    echo ""
    echo "2. 查看日志:"
    if [ "$PROTOCOL" = "hysteria2" ]; then
        echo "   客户端: ssh -p 9321 root@47.117.159.145 'journalctl -u hysteria2-client -f'"
        echo "   服务端: ssh -p 22 root@8.162.10.216 'journalctl -u hysteria2-server -f'"
    else
        echo "   服务端: ssh -p 22 root@8.162.10.216 'journalctl -u frp-quic -f'"
    fi
    echo ""
    echo "3. 测试SOCKS5代理 (Hysteria2):"
    echo "   ssh -p 9321 root@47.117.159.145"
    echo "   curl -x socks5://127.0.0.1:1080 http://www.baidu.com"
    echo ""
    echo "4. 配置客户端使用代理:"
    if [ "$PROTOCOL" = "hysteria2" ]; then
        echo "   SOCKS5代理: 47.117.159.145:1080"
    fi
    echo ""
    echo "========================================"
    echo ""
}

# 主函数
main() {
    show_banner
    
    # 检查环境
    check_python
    install_dependencies
    
    # 配置
    select_protocol
    configure_servers
    configure_port
    
    # 确认
    echo ""
    log_warn "即将开始部署，请确认:"
    echo "  协议: $PROTOCOL"
    echo "  服务端端口: $SERVER_PORT"
    echo ""
    read -p "确认开始? [Y/n]: " confirm
    
    if [[ ! "$confirm" =~ ^[Nn]$ ]]; then
        # 部署
        if deploy; then
            # 验证
            verify
            # 显示后续步骤
            show_next_steps
        else
            log_error "部署失败，请检查错误信息"
            exit 1
        fi
    else
        log_info "已取消部署"
    fi
}

# 运行主函数
main
