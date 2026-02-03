# FRP服务自动化部署文档

## 📋 目录

1. [项目概述](#项目概述)
2. [环境要求](#环境要求)
3. [快速开始](#快速开始)
4. [详细部署步骤](#详细部署步骤)
5. [协议选择](#协议选择)
6. [验证测试](#验证测试)
7. [故障排查](#故障排查)
8. [交付标准](#交付标准)

---

## 项目概述

本项目提供完整的FRP（Fast Reverse Proxy）服务自动化部署方案，支持以下协议：

- **Hysteria2**: 基于QUIC的高性能代理协议，速度极快
- **Python QUIC**: 纯Python实现的QUIC协议，便于定制

### 架构说明

```
客户端服务器 (47.117.159.145:9321)
    ↓ Hysteria2/QUIC 连接
服务端服务器 (8.162.10.216:22)
```

---

## 环境要求

### 控制端（本地机器）

- Python 3.7+
- 网络连接到两台服务器

### 服务器环境

**操作系统支持**:
- Ubuntu 18.04+
- Debian 10+
- CentOS 7+
- Alpine Linux

**系统要求**:
- Root权限
- 至少512MB内存
- 端口开放（4433或7000）

---

## 快速开始

### 1. 安装依赖

```bash
cd deploy
pip install -r requirements.txt
```

### 2. 配置服务器信息

编辑 `auto_deploy.py`，修改服务器连接信息：

```python
CLIENT_SERVER = {
    'host': '47.117.159.145',
    'port': 9321,
    'username': 'root',
    'password': 'uUyb-ARfcT=D2mMpBn(L'
}

SERVER_SERVER = {
    'host': '8.162.10.216',
    'port': 22,
    'username': 'root',
    'password': 'JeiFing1234@'
}
```

### 3. 执行自动化部署

**部署Hysteria2（推荐）**:
```bash
python auto_deploy.py --protocol hysteria2
```

**部署Python QUIC**:
```bash
python auto_deploy.py --protocol quic
```

### 4. 验证部署

```bash
python verify_deployment.py --protocol hysteria2
```

---

## 详细部署步骤

### 步骤1: 准备工作

#### 1.1 检查本地环境

```bash
# 检查Python版本
python --version  # 需要 >= 3.7

# 安装依赖
pip install paramiko cryptography
```

#### 1.2 测试服务器连接

```bash
# 测试SSH连接
python ssh_manager.py

# 应该看到：
# ✓ 客户端服务器连接成功
# ✓ 服务端服务器连接成功
```

### 步骤2: 部署Hysteria2

#### 2.1 执行自动化部署

```bash
python auto_deploy.py --protocol hysteria2 --server-port 4433
```

**参数说明**:
- `--protocol`: 协议类型（hysteria2/quic）
- `--server-port`: 服务端端口（默认4433）
- `--domain`: 域名（可选，用于SSL证书）

#### 2.2 部署流程

脚本会自动执行以下步骤：

1. **连接测试**: 验证SSH连接
2. **环境准备**: 安装依赖包
3. **服务端安装**: 
   - 下载Hysteria2二进制文件
   - 生成SSL证书
   - 配置服务端
   - 创建systemd服务
4. **客户端安装**:
   - 下载Hysteria2客户端
   - 配置SOCKS5代理
   - 创建systemd服务
5. **服务启动**: 启动并启用服务
6. **自动验证**: 测试连通性

#### 2.3 部署输出示例

```
→ 测试服务器连接...
✓ 客户端服务器连接成功
✓ 服务端服务器连接成功

→ 准备客户端运行环境...
✓ 客户端环境准备完成

→ 准备服务端运行环境...
✓ 服务端环境准备完成

→ 安装Hysteria2服务端...
✓ Hysteria2服务端安装完成
服务端认证密码: abc123xyz

→ 安装Hysteria2客户端...
✓ Hysteria2客户端安装完成

→ 启动服务...
✓ 服务启动完成

→ 验证部署...
✓ SOCKS5代理连接测试成功

========================================
部署完成
========================================
```

### 步骤3: 部署Python QUIC

```bash
python auto_deploy.py --protocol quic --server-port 7000
```

部署流程类似，但使用Python实现的QUIC协议。

### 步骤4: 配置防火墙

如果服务器使用防火墙，需要开放端口：

**UFW (Ubuntu/Debian)**:
```bash
# Hysteria2
sudo ufw allow 4433/tcp
sudo ufw allow 4433/udp

# Python QUIC
sudo ufw allow 7000/tcp
sudo ufw allow 7000/udp
```

**firewalld (CentOS)**:
```bash
sudo firewall-cmd --permanent --add-port=4433/tcp
sudo firewall-cmd --permanent --add-port=4433/udp
sudo firewall-cmd --reload
```

---

## 协议选择

### Hysteria2 vs Python QUIC

| 特性 | Hysteria2 | Python QUIC |
|------|-----------|-------------|
| **性能** | ⭐⭐⭐⭐⭐ 极快 | ⭐⭐⭐ 中等 |
| **速度** | 80-100 MB/s | 15-20 MB/s |
| **弱网表现** | 优秀 | 良好 |
| **易用性** | 简单 | 中等 |
| **定制性** | 低 | 高 |
| **推荐场景** | 生产环境 | 开发/定制 |

### 推荐方案

**生产环境**: Hysteria2
- 性能极佳
- 稳定可靠
- 适合弱网

**开发测试**: Python QUIC
- 纯Python实现
- 便于调试
- 易于定制

---

## 验证测试

### 自动验证

```bash
python verify_deployment.py --protocol hysteria2
```

验证脚本会检查：
- ✓ 服务运行状态
- ✓ 端口监听状态
- ✓ 网络连通性
- ✓ SOCKS5代理功能
- ✓ 性能指标
- ✓ 错误日志

### 手动验证

#### 1. 检查服务状态

**客户端服务器**:
```bash
# Hysteria2
systemctl status hysteria2-client

# Python QUIC
systemctl status frp-quic
```

**服务端服务器**:
```bash
# Hysteria2
systemctl status hysteria2-server

# Python QUIC
systemctl status frp-quic
```

#### 2. 检查端口监听

```bash
# 客户端服务器
ss -tuln | grep -E ':(1080|4433)'

# 服务端服务器
ss -tuln | grep -E ':(4433|7000)'
```

#### 3. 测试SOCKS5代理（Hysteria2）

```bash
# 在客户端服务器上测试
curl -x socks5://127.0.0.1:1080 http://www.baidu.com -I
```

#### 4. 查看日志

```bash
# Hysteria2
journalctl -u hysteria2-server -f
journalctl -u hysteria2-client -f

# Python QUIC
journalctl -u frp-quic -f
```

#### 5. 性能测试

```bash
# 延迟测试
curl -x socks5://127.0.0.1:1080 -w "%{time_total}" -o /dev/null -s http://www.baidu.com

# 下载速度测试
curl -x socks5://127.0.0.1:1080 http://speedtest.tele2.net/1MB.zip -o /tmp/test
```

---

## 故障排查

### 问题1: SSH连接失败

**症状**: `✗ 连接超时` 或 `✗ 认证失败`

**解决方案**:
1. 检查服务器IP和端口是否正确
2. 确认密码/密钥是否正确
3. 检查服务器SSH服务是否运行
4. 检查防火墙是否阻止SSH端口

```bash
# 测试SSH连接
ssh -p 9321 root@47.117.159.145
```

### 问题2: 服务无法启动

**症状**: `✗ 服务端启动失败`

**解决方案**:

1. 查看详细日志:
```bash
journalctl -u hysteria2-server -n 50
```

2. 检查配置文件:
```bash
cat /etc/hysteria2/config.yaml
```

3. 检查端口占用:
```bash
ss -tuln | grep 4433
```

4. 检查证书文件:
```bash
ls -la /etc/hysteria2/
```

### 问题3: 无法连接到服务

**症状**: `✗ 客户端→服务端: 不通`

**解决方案**:

1. 检查防火墙:
```bash
# 开放端口
sudo ufw allow 4433/tcp
sudo ufw allow 4433/udp
```

2. 检查云服务商安全组:
   - 登录云控制台
   - 添加安全组规则，开放端口4433

3. 测试端口连通性:
```bash
nc -zv 8.162.10.216 4433
```

### 问题4: SOCKS5代理不工作

**症状**: `✗ SOCKS5代理: 测试失败`

**解决方案**:

1. 检查客户端配置:
```bash
cat /etc/hysteria2/client.yaml
```

2. 重启客户端服务:
```bash
systemctl restart hysteria2-client
```

3. 检查服务端认证密码:
```bash
grep 'password:' /etc/hysteria2/config.yaml
```

确保客户端和服务端密码一致。

### 问题5: 速度慢

**症状**: 下载速度远低于预期

**解决方案**:

1. 调整带宽配置（服务端）:
```bash
nano /etc/hysteria2/config.yaml

# 修改带宽参数
bandwidth:
  up: 1 gbps
  down: 1 gbps
```

2. 重启服务:
```bash
systemctl restart hysteria2-server
```

3. 检查网络质量:
```bash
# 测试延迟
ping 8.162.10.216

# 测试丢包
mtr 8.162.10.216
```

---

## 交付标准

### 1. 部署脚本

✅ `auto_deploy.py` - 自动化部署脚本
✅ `verify_deployment.py` - 验证测试脚本
✅ `ssh_manager.py` - SSH连接管理
✅ `hysteria2_installer.sh` - Hysteria2安装脚本

### 2. 配置文件

✅ `deployment_config.json` - 部署配置（自动生成）
✅ `/etc/hysteria2/config.yaml` - 服务端配置
✅ `/etc/hysteria2/client.yaml` - 客户端配置

### 3. 服务状态

✅ 服务端服务运行正常
✅ 客户端服务运行正常
✅ 服务开机自启已启用
✅ 防火墙规则已配置

### 4. 测试报告

✅ 网络连通性测试通过
✅ SOCKS5代理功能正常
✅ 性能测试符合预期
✅ 日志无异常错误

### 5. 文档

✅ 本部署文档
✅ 故障排查指南
✅ 验证测试报告

---

## 附录

### A. 常用命令

```bash
# 服务管理
systemctl start hysteria2-server    # 启动服务端
systemctl stop hysteria2-server     # 停止服务端
systemctl restart hysteria2-server  # 重启服务端
systemctl status hysteria2-server   # 查看状态

# 日志查看
journalctl -u hysteria2-server -f      # 实时日志
journalctl -u hysteria2-server -n 50   # 最近50行
journalctl -u hysteria2-server --since today  # 今天的日志

# 配置测试
hysteria2 client -c /etc/hysteria2/client.yaml  # 测试客户端配置
hysteria2 server -c /etc/hysteria2/config.yaml  # 测试服务端配置

# 端口检查
ss -tuln | grep 4433
netstat -tuln | grep 4433
lsof -i :4433
```

### B. 配置文件示例

**Hysteria2服务端配置** (`/etc/hysteria2/config.yaml`):

```yaml
# 监听端口
listen: :4433

# TLS配置
tls:
  cert: /etc/hysteria2/cert.pem
  key: /etc/hysteria2/key.pem

# 认证配置
auth:
  type: password
  password: your_password_here

# 带宽配置
bandwidth:
  up: 1 gbps
  down: 1 gbps

# QUIC参数
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
```

### C. 性能优化建议

1. **启用BBR拥塞控制** (Linux 4.9+):
```bash
echo 'net.core.default_qdisc=fq' >> /etc/sysctl.conf
echo 'net.ipv4.tcp_congestion_control=bbr' >> /etc/sysctl.conf
sysctl -p
```

2. **调整系统参数**:
```bash
# 增加文件描述符限制
echo '* soft nofile 1048576' >> /etc/security/limits.conf
echo '* hard nofile 1048576' >> /etc/security/limits.conf

# 优化网络参数
echo 'net.ipv4.tcp_fastopen=3' >> /etc/sysctl.conf
echo 'net.ipv4.tcp_slow_start_after_idle=0' >> /etc/sysctl.conf
sysctl -p
```

3. **使用域名和Let's Encrypt证书**:
```bash
python auto_deploy.py --protocol hysteria2 --domain your-domain.com --email your@email.com
```

---

## 联系支持

如有问题，请查看故障排查部分或提交Issue。

---

**部署完成后，请保存以下信息**:

- 服务端地址: 8.162.10.216:4433
- 认证密码: (查看部署输出或 `/etc/hysteria2/config.yaml`)
- 客户端SOCKS5端口: 1080

**祝您使用愉快！** 🎉
