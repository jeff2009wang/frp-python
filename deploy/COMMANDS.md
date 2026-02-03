# 🚀 Bash部署命令参考

## 一键部署命令

### 完整自动化部署

```bash
# 进入部署目录
cd d:\frp-python\deploy

# 运行一键部署脚本
bash deploy.sh
```

---

## 分步部署命令

### 1. 安装依赖

```bash
# Linux (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y sshpass curl wget python3 python3-pip

# Linux (CentOS/RHEL)
sudo yum install -y sshpass curl wget python3 python3-pip

# Mac
brew install sshpass
```

### 3. 准备服务器环境

```bash
# 客户端服务器
sshpass -p "uUyb-ARfcT=D2mMpBn(L)" ssh -p 9321 root@47.117.159.145 "
apt-get update -qq && \
apt-get install -y -qq curl wget python3 python3-pip openssl systemd && \
mkdir -p /opt/frp-service
"

# 服务端服务器
sshpass -p "JeiFing1234@" ssh -p 22 root@8.162.10.216 "
apt-get update -qq && \
apt-get install -y -qq curl wget python3 python3-pip openssl systemd && \
mkdir -p /opt/frp-service
"
```

### 4. 安装Hysteria2

#### 4.1 安装服务端

```bash
# 下载Hysteria2
sshpass -p "JeiFing1234@" ssh -p 22 root@8.162.10.216 "
ARCH=\$(uname -m) && \
case \$ARCH in
    x86_64) BINARY='hysteria2-linux-amd64' ;;
    aarch64|arm64) BINARY='hysteria2-linux-arm64' ;;
    armv7l) BINARY='hysteria2-linux-armv7' ;;
    *) echo 'Unsupported' && exit 1 ;;
esac && \
curl -L -o /usr/local/bin/hysteria2 https://github.com/apernet/hysteria2/releases/latest/download/\$BINARY && \
chmod +x /usr/local/bin/hysteria2
"

# 生成证书和配置
sshpass -p "JeiFing1234@" ssh -p 22 root@8.162.10.216 "
mkdir -p /etc/hysteria2 && \
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout /etc/hysteria2/key.pem \
  -out /etc/hysteria2/cert.pem \
  -subj '/CN=Hysteria2-Server/O=Hysteria2/C=US' && \
PASSWORD=\$(openssl rand -base64 16) && \
cat > /etc/hysteria2/config.yaml << EOF
listen: :4433
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
echo '密码: '\${PASSWORD}
"

# 创建systemd服务
sshpass -p "JeiFing1234@" ssh -p 22 root@8.162.10.216 "
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

systemctl daemon-reload && \
systemctl enable hysteria2-server && \
systemctl start hysteriaia2-server && \
sleep 2 && \
systemctl status hysteriaia2-server --no-pager
"
```

#### 4.2 安装客户端

```bash
# 下载Hysteria2客户端
sshpass -p "uUyb-ARfcT=D2mMpBn(L)" ssh -p 9321 root@47.117.159.145 "
ARCH=\$(uname -m) && \
case \$ARCH in
    x86_64) BINARY='hysteria2-linux-amd64' ;;
    aarch64|arm64) BINARY='hysteria2-linux-arm64' ;;
    armv7l) BINARY='hysteria2-linux-armv7' ;;
    *) echo 'Unsupported' && exit 1 ;;
esac && \
curl -L -o /usr/local/bin/hysteria2 https://github.com/apernet/hysteria2/releases/latest/download/\$BINARY && \
chmod +x /usr/local/bin/hysteria2
"

# 获取服务端密码
SERVER_PASSWORD=$(sshpass -p "JeiFing1234@" ssh -p 22 root@8.162.10.216 "grep 'password:' /etc/hysteria2/config.yaml | awk '{print \$2}'" | tr -d '\r\n')

# 生成客户端配置
sshpass -p "uUyb-ARfcT=D2mMpBn(L)" ssh -p 9321 root@47.117.159.145 "
mkdir -p /etc/hysteria2 && \
cat > /etc/hysteria2/client.yaml << EOF
server: 8.162.10.216:4433
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
"

# 创建systemd服务
sshpass -p "uUyb-ARfcT=D2mMpBn(L)" ssh -p 9321 root@47.117.159.145 "
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

systemctl daemon-reload && \
systemctl enable hysteria2-client && \
systemctl start hysteria2-client && \
sleep 2 && \
systemctl status hysteria2-client --no-pager
"
```

### 5. 配置防火墙

```bash
# 服务端防火墙 (UFW)
sshpass -p "JeiFing1234@" ssh -p 22 root@8.162.10.216 "
ufw allow 4433/tcp && \
ufw allow 4433/udp && \
ufw status
"

# 服务端防火墙 (firewalld)
sshpass -p "JeiFing1234@" ssh -p 22 root@8.162.10.216 "
firewall-cmd --permanent --add-port=4433/tcp && \
firewall-cmd --permanent --add-port=4433/udp && \
firewall-cmd --reload && \
firewall-cmd --list-ports
"
```

### 6. 验证部署

```bash
# 检查服务端状态
sshpass -p "JeiFing1234@" ssh -p 22 root@8.162.10.216 "
systemctl is-active hysteria2-server && \
ss -tuln | grep 4433
"

# 检查客户端状态
sshpass -p "uUyb-ARfcT=D2mMpBn(L)" ssh -p 9321 root@47.117.159.145 "
systemctl is-active hysteria2-client && \
ss -tuln | grep 1080
"

# 测试SOCKS5代理
sshpass -p "uUyb-ARfcT=D2mMpBn(L)" ssh -p 9321 root@47.117.159.145 "
curl -x socks5://127.0.0.1:1080 http://www.baidu.com -I -s
"
```

---

## 快速命令集

### 完整一键部署

```bash
cd d:\frp-python\deploy && bash deploy.sh
```

### 只部署Hysteria2

```bash
cd d:\frp-python\deploy && bash deploy.sh 2>&1 | grep -E "(INFO|STEP|ERROR)"
```

### 查看服务状态

```bash
# 服务端
sshpass -p "JeiFing1234@" ssh -p 22 root@8.162.10.216 "systemctl status hysteria2-server"

# 客户端
sshpass -p "uUyb-ARfcT=D2mMpBn(L)" ssh -p 9321 root@47.117.159.145 "systemctl status hysteria2-client"
```

### 查看日志

```bash
# 服务端日志
sshpass -p "JeiFing1234@" ssh -p 22 root@8.162.10.216 "journalctl -u hysteria2-server -f"

# 客户端日志
sshpass -p "uUyb-ARfcT=D2mMpBn(L)" ssh -p 9321 root@47.117.159.145 "journalctl -u hysteria2-client -f"
```

### 重启服务

```bash
# 重启服务端
sshpass -p "JeiFing1234@" ssh -p 22 root@8.162.10.216 "systemctl restart hysteria2-server"

# 重启客户端
sshpass -p "uUyb-ARfcT=D2mMpBn(L)" ssh -p 9321 root@47.117.159.145 "systemctl restart hysteria2-client"
```

### 停止服务

```bash
# 停止服务端
sshpass -p "JeiFing1234@" ssh -p 22 root@8.162.10.216 "systemctl stop hysteria2-server"

# 停止客户端
sshpass -p "uUyb-ARfcT=D2mMpBn(L)" ssh -p 9321 root@47.117.159.145 "systemctl stop hysteria2-client"
```

---

## 变量说明

可在脚本开头修改以下变量：

```bash
# 服务器配置
CLIENT_HOST="47.117.159.145"    # 客户端服务器IP
CLIENT_PORT="9321"              # 客户端SSH端口
CLIENT_USER="root"              # 客户端用户名
CLIENT_PASS="uUyb-ARfcT=D2mMpBn(L)"  # 客户端密码

SERVER_HOST="8.162.10.216"      # 服务端服务器IP
SERVER_PORT="22"                # 服务端SSH端口
SERVER_USER="root"              # 服务端用户名
SERVER_PASS="JeiFing1234@"      # 服务端密码

PROTOCOL="hysteria2"            # 协议: hysteria2 或 quic
SERVER_PORT_NUM="4433"          # 服务监听端口
```

---

## 常见问题

### Q: 如何查看Hysteria2密码？

```bash
sshpass -p "JeiFing1234@" ssh -p 22 root@8.162.10.216 "grep 'password:' /etc/hysteria2/config.yaml"
```

### Q: 如何修改端口？

修改 `deploy.sh` 中的 `SERVER_PORT_NUM` 变量，然后重新运行。

### Q: 如何卸载？

```bash
# 服务端
sshpass -p "JeiFing1234@" ssh -p 22 root@8.162.10.216 "
systemctl stop hysteria2-server && \
systemctl disable hysteria2-server && \
rm -f /etc/systemd/system/hysteria2-server.service && \
rm -rf /etc/hysteria2 && \
rm -f /usr/local/bin/hysteria2 && \
systemctl daemon-reload
"

# 客户端
sshpass -p "uUyb-ARfcT=D2mMpBn(L)" ssh -p 9321 root@47.117.159.145 "
systemctl stop hysteria2-client && \
systemctl disable hysteria2-client && \
rm -f /etc/systemd/system/hysteria2-client.service && \
rm -rf /etc/hysteria2 && \
rm -f /usr/local/bin/hysteria2 && \
systemctl daemon-reload
"
```

---

## 直接复制运行

### 最简单的一行命令

```bash
cd d:\frp-python\deploy && bash deploy.sh 2>&1 | tee deploy.log
```

### 仅输出错误和重要信息

```bash
cd d:\frp-python\deploy && bash deploy.sh 2>&1 | grep -E "(ERROR|INFO|STEP|✓|✗)"
```

### 后台运行

```bash
cd d:\frp-python\deploy && nohup bash deploy.sh > deploy.log 2>&1 &
```

---

**开始部署**:

```bash
bash d:\frp-python\deploy\deploy.sh
```
