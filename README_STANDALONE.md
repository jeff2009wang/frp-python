# FRP-Python 独立可执行版本

## 快速开始

### 服务端 (frps.exe)

```bash
frps.exe <frps_port> <user_port>
```

**示例**：
```bash
frps.exe 7000 8001
```

- `frps_port`：客户端连接端口（7000）
- `user_port`：对外访问端口（8001）

---

### 客户端 (frpc.exe)

```bash
frpc.exe <server_host> <server_port> [options]
```

**基础示例**：
```bash
frpc.exe 192.168.1.100 7000
```

**监控指定端口**：
```bash
frpc.exe 192.168.1.100 7000 --ports 22,80,3389
```

**完整参数**：
- `--target HOST`：要扫描的目标主机（默认：localhost）
- `--interval SECONDS`：扫描间隔（默认：30）
- `--pool-size NUM`：连接池大小（默认：5）
- `--ports PORTS`：要监控的端口列表，逗号分隔（默认：所有端口）
- `--stable-time SECONDS`：端口稳定时间（默认：10）
- `--status`：显示当前状态并退出

---

## 使用场景

### 场景：自动穿透多个服务

**服务端**（公网服务器 123.45.67.89）：
```bash
frps.exe 7000 8001
```

**客户端**（内网机器）：
```bash
frpc.exe 123.45.67.89 7000 --ports 22,80,443,3389,8080
```

**效果**：
- 启动 SSH（端口 22）→ 自动通过 `123.45.67.89:22` 访问
- 启动 Web（端口 80）→ 自动通过 `123.45.67.89:80` 访问
- 启动 RDP（端口 3389）→ 自动通过 `123.45.67.89:3389` 访问
- 服务关闭后，对应穿透自动停止

---

## 编译说明

### 重新编译

```bash
python build.py
```

### 单独编译

**服务端**：
```bash
pyinstaller --onefile --name frps --console --clean frps_standalone.py
```

**客户端**：
```bash
pyinstaller --onefile --name frpc --console --clean frpc_standalone.py
```

---

## 特性

- **单文件运行**：无需 Python 环境，直接运行
- **自动端口扫描**：定期扫描本地端口
- **智能 FRP 管理**：自动创建/关闭 FRP 连接
- **低延迟传输**：TCP_NODELAY + 64KB 缓冲区
- **自动重连**：连接断开自动恢复
- **连接池**：预建立连接，减少延迟

---

## 文件说明

| 文件 | 说明 |
|------|------|
| frps.exe | 服务端可执行文件 |
| frpc.exe | 客户端可执行文件 |
| frps_standalone.py | 服务端源码 |
| frpc_standalone.py | 客户端源码 |
| build.py | 编译脚本 |
| README_BUILD.md | 详细编译指南 |
