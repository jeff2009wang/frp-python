# FRP-Python 编译指南

## 快速开始

### 1. 安装依赖

```bash
pip install pyinstaller
```

### 2. 编译所有可执行文件

```bash
python build.py
```

这将编译服务端和客户端，生成 `dist/frps.exe` 和 `dist/frpc.exe`

### 3. 分别编译

**只编译服务端**：
```bash
python build.py server
```

**只编译客户端**：
```bash
python build.py client
```

## 使用编译后的文件

### 服务端 (frps.exe)

```bash
frps.exe <frps_port> <user_port>
```

示例：
```bash
frps.exe 7000 8001
```

### 客户端 (frpc.exe)

```bash
frpc.exe <server_host> <server_port> [options]
```

示例：
```bash
frpc.exe 192.168.1.100 7000 --ports 22,80,3389
```

## 平台支持

- **Windows**: 生成 `.exe` 文件
- **Linux**: 生成可执行文件

## 手动编译（使用 PyInstaller）

### 服务端

```bash
pyinstaller --onefile --name frps --console --clean frps_standalone.py
```

### 客户端

```bash
pyinstaller --onefile --name frpc --console --clean frpc_standalone.py
```

## 文件说明

| 文件 | 说明 |
|------|------|
| frps_standalone.py | 服务端源码（单文件） |
| frpc_standalone.py | 客户端源码（单文件） |
| build.py | 编译脚本 |
| frps.spec | 服务端 PyInstaller 配置 |
| frpc.spec | 客户端 PyInstaller 配置 |
| dist/frps.exe | 编译后的服务端 |
| dist/frpc.exe | 编译后的客户端 |

## 特性

- **单文件运行**：无需依赖，直接运行
- **自动端口扫描**：客户端自动发现运行中的服务
- **低延迟传输**：TCP_NODELAY + 64KB 缓冲区
- **自动重连**：连接断开自动恢复
- **连接池**：预建立连接，减少延迟
