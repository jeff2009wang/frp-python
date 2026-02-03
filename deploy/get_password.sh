#!/bin/bash
###############################################################################
# 获取FRP服务端密码脚本
# 从服务端获取Hysteria2认证密码
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

# 获取参数
SERVER_HOST=${1:-8.162.10.216}
SERVER_PORT=${2:-4433}

log_info "正在从 ${SERVER_HOST}:${SERVER_PORT} 获取服务端密码..."

# 方法1: 尝试从服务端配置文件读取
if [ -f "/etc/hysteria2/config.yaml" ]; then
    PASSWORD=$(grep "password:" /etc/hysteria2/config.yaml | awk '{print $2}' | head -1)
    if [ -n "$PASSWORD" ]; then
        echo "$PASSWORD"
        exit 0
    fi
fi

# 方法2: 尝试从服务端日志获取
if command -v journalctl &> /dev/null; then
    PASSWORD=$(journalctl -u hysteria2-server --no-pager -n 100 | grep -i "password" | tail -1 | grep -o '[a-zA-Z0-9+/]\{16,\}' | head -1)
    if [ -n "$PASSWORD" ]; then
        echo "$PASSWORD"
        exit 0
    fi
fi

# 方法3: 尝试从服务端API获取（如果存在）
if command -v curl &> /dev/null; then
    # 尝试访问服务端状态接口
    RESPONSE=$(curl -s --connect-timeout 5 "http://${SERVER_HOST}:${SERVER_PORT}/status" 2>/dev/null || echo "")
    if [ -n "$RESPONSE" ]; then
        PASSWORD=$(echo "$RESPONSE" | grep -o '"password":"[^"]*"' | cut -d'"' -f4 | head -1)
        if [ -n "$PASSWORD" ]; then
            echo "$PASSWORD"
            exit 0
        fi
    fi
fi

# 方法4: 尝试从环境变量获取
if [ -n "$HYSTERIA2_PASSWORD" ]; then
    echo "$HYSTERIA2_PASSWORD"
    exit 0
fi

# 方法5: 尝试从文件获取
if [ -f "/tmp/hysteria2_password.txt" ]; then
    PASSWORD=$(cat /tmp/hysteria2_password.txt 2>/dev/null | head -1)
    if [ -n "$PASSWORD" ]; then
        echo "$PASSWORD"
        exit 0
    fi
fi

# 方法6: 生成默认密码（用于测试）
log_warn "无法获取服务端密码，使用默认密码"
echo "default_password_123"