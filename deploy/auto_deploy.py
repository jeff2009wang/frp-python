#!/usr/bin/env python3
"""
自动化部署脚本
支持Hysteria2和Python QUIC两种协议的自动部署
"""

import sys
import os
import time
import json
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent))
from ssh_manager import SSHManager, CLIENT_SERVER, SERVER_SERVER

# 部署配置
DEPLOYMENT_CONFIG = {
    'protocol': 'hysteria2',  # 'hysteria2' or 'quic'
    'hysteria2': {
        'server_port': 4433,
        'client_local_port': 1080,
        'domain': '',  # 留空使用自签名证书
    },
    'quic': {
        'server_port': 7000,
        'cert_path': '/etc/frp-quic/server_cert.pem',
        'key_path': '/etc/frp-quic/server_key.pem',
    },
    'project_dir': '/opt/frp-service',
}


class DeploymentManager:
    def __init__(self, client_server: dict, server_server: dict, config: dict):
        self.client_config = client_server
        self.server_config = server_server
        self.deploy_config = config
        self.client_ssh = None
        self.server_ssh = None
    
    def log(self, message: str, level: str = 'INFO'):
        """日志输出"""
        prefix = {
            'INFO': '✓',
            'WARN': '⚠',
            'ERROR': '✗',
            'STEP': '→'
        }.get(level, '•')
        print(f"{prefix} {message}")
    
    def test_connections(self) -> bool:
        """测试两台服务器的连接"""
        self.log("测试服务器连接...", 'STEP')
        
        # 连接客户端服务器
        self.log(f"连接客户端服务器: {self.client_config['host']}", 'INFO')
        self.client_ssh = SSHManager(**self.client_config)
        if not self.client_ssh.connect():
            self.log("客户端服务器连接失败", 'ERROR')
            return False
        
        # 连接服务端服务器
        self.log(f"连接服务端服务器: {self.server_config['host']}", 'INFO')
        self.server_ssh = SSHManager(**self.server_config)
        if not self.server_ssh.connect():
            self.log("服务端服务器连接失败", 'ERROR')
            return False
        
        self.log("两台服务器连接成功", 'INFO')
        return True
    
    def prepare_environment(self, ssh: SSHManager, server_type: str) -> bool:
        """准备运行环境"""
        self.log(f"准备{server_type}运行环境...", 'STEP')
        
        # 更新系统包
        self.log("更新系统包...", 'INFO')
        ssh.execute_command('apt-get update -qq || yum update -y -q')
        
        # 安装基础依赖
        self.log("安装基础依赖...", 'INFO')
        ssh.execute_command('apt-get install -y -qq curl wget python3 python3-pip openssl systemd || yum install -y -q curl wget python3 python3-pip openssl systemd')
        
        # 创建项目目录
        project_dir = self.deploy_config['project_dir']
        self.log(f"创建项目目录: {project_dir}", 'INFO')
        ssh.execute_command(f'mkdir -p {project_dir}')
        
        self.log(f"{server_type}环境准备完成", 'INFO')
        return True
    
    def install_hysteria2_server(self) -> bool:
        """安装Hysteria2服务端"""
        self.log("安装Hysteria2服务端...", 'STEP')
        
        # 读取安装脚本
        script_path = Path(__file__).parent / 'hysteria2_installer.sh'
        if not script_path.exists():
            self.log("安装脚本不存在", 'ERROR')
            return False
        
        with open(script_path, 'r', encoding='utf-8') as f:
            script_content = f.read()
        
        # 上传并执行安装脚本
        port = self.deploy_config['hysteria2']['server_port']
        domain = self.deploy_config['hysteria2'].get('domain', '')
        
        install_cmd = f"bash -s -- --port {port}"
        if domain:
            install_cmd += f" --domain {domain}"
        
        exit_code, output, error = self.server_ssh.execute_script(script_content, '/tmp/hy2_install.sh')
        
        if exit_code != 0:
            self.log(f"Hysteria2服务端安装失败: {error}", 'ERROR')
            return False
        
        self.log("Hysteria2服务端安装完成", 'INFO')
        
        # 获取认证密码
        exit_code, output, _ = self.server_ssh.execute_command("grep 'password:' /etc/hysteria2/config.yaml | awk '{print $2}'")
        if exit_code == 0:
            password = output.strip()
            self.log(f"服务端认证密码: {password}", 'INFO')
            self.deploy_config['hysteria2']['password'] = password
        
        return True
    
    def install_hysteria2_client(self) -> bool:
        """安装Hysteria2客户端"""
        self.log("安装Hysteria2客户端...", 'STEP')
        
        # 下载客户端
        arch_cmd = "uname -m"
        exit_code, arch, _ = self.client_ssh.execute_command(arch_cmd)
        
        if 'x86_64' in arch:
            binary = 'hysteria2-linux-amd64'
        elif 'aarch64' in arch or 'arm64' in arch:
            binary = 'hysteria2-linux-arm64'
        else:
            binary = 'hysteria2-linux-armv7'
        
        download_cmd = f"curl -L -o /usr/local/bin/hysteria2 https://github.com/apernet/hysteria2/releases/latest/download/{binary}"
        exit_code, _, error = self.client_ssh.execute_command(download_cmd)
        
        if exit_code != 0:
            self.log(f"Hysteria2客户端下载失败: {error}", 'ERROR')
            return False
        
        self.client_ssh.execute_command('chmod +x /usr/local/bin/hysteria2')
        
        # 生成客户端配置
        server_addr = self.server_config['host']
        server_port = self.deploy_config['hysteria2']['server_port']
        password = self.deploy_config['hysteria2'].get('password', 'default_password')
        local_port = self.deploy_config['hysteria2']['client_local_port']
        
        config = f"""# Hysteria2 客户端配置
server: {server_addr}:{server_port}

auth:
  type: password
  password: {password}

socks5:
  listen: 127.0.0.1:{local_port}

# 快速连接
fastOpen: true
lazy: true

# 日志配置
log:
  level: info
"""
        
        config_cmd = f"cat > /etc/hysteria2/client.yaml << 'EOF'\n{config}\nEOF"
        exit_code, _, error = self.client_ssh.execute_command(config_cmd)
        
        if exit_code != 0:
            self.log(f"客户端配置生成失败: {error}", 'ERROR')
            return False
        
        # 创建systemd服务
        service_content = """[Unit]
Description=Hysteria2 Client Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/hysteria2 client -c /etc/hysteria2/client.yaml
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
"""
        
        self.client_ssh.execute_command("cat > /etc/systemd/system/hysteria2-client.service << 'EOF'\n" + service_content + "EOF")
        self.client_ssh.execute_command('systemctl daemon-reload')
        self.client_ssh.execute_command('systemctl enable hysteria2-client')
        
        self.log("Hysteria2客户端安装完成", 'INFO')
        return True
    
    def install_quic_server(self) -> bool:
        """安装Python QUIC服务端"""
        self.log("安装Python QUIC服务端...", 'STEP')
        
        # 安装Python依赖
        self.log("安装Python依赖...", 'INFO')
        pip_install = 'pip3 install aioquic pyOpenSSL certifi'
        exit_code, _, error = self.server_ssh.execute_command(pip_install)
        
        if exit_code != 0:
            self.log(f"Python依赖安装失败: {error}", 'ERROR')
            return False
        
        # 创建证书目录
        cert_dir = os.path.dirname(self.deploy_config['quic']['cert_path'])
        self.server_ssh.execute_command(f'mkdir -p {cert_dir}')
        
        # 生成自签名证书
        self.log("生成SSL证书...", 'INFO')
        gen_cert = f"""openssl req -x509 -newkey rsa:2048 -nodes -days 365 \\
        -keyout {self.deploy_config['quic']['key_path']} \\
        -out {self.deploy_config['quic']['cert_path']} \\
        -subj "/CN=FRP-QUIC-Server"""
        self.server_ssh.execute_command(gen_cert)
        
        # 上传服务端代码
        self.log("上传服务端代码...", 'INFO')
        server_code_path = Path(__file__).parent.parent / 'version_quic_pure_python' / 'frps_quic.py'
        if not server_code_path.exists():
            self.log("服务端代码文件不存在", 'ERROR')
            return False
        
        self.server_ssh.upload_file(str(server_code_path), f"{self.deploy_config['project_dir']}/frps_quic.py")
        self.server_ssh.upload_file(str(server_code_path.parent / 'server_cert.pem'), self.deploy_config['quic']['cert_path'])
        self.server_ssh.upload_file(str(server_code_path.parent / 'server_key.pem'), self.deploy_config['quic']['key_path'])
        
        # 创建systemd服务
        port = self.deploy_config['quic']['server_port']
        service_content = f"""[Unit]
Description=FRP QUIC Server
After=network.target

[Service]
Type=simple
WorkingDirectory={self.deploy_config['project_dir']}
ExecStart=/usr/bin/python3 {self.deploy_config['project_dir']}/frps_quic.py {port}
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
"""
        
        self.server_ssh.execute_command(f"cat > /etc/systemd/system/frp-quic.service << 'EOF'\n{service_content}\nEOF")
        self.server_ssh.execute_command('systemctl daemon-reload')
        self.server_ssh.execute_command('systemctl enable frp-quic')
        
        self.log("Python QUIC服务端安装完成", 'INFO')
        return True
    
    def start_services(self) -> bool:
        """启动服务"""
        self.log("启动服务...", 'STEP')
        
        if self.deploy_config['protocol'] == 'hysteria2':
            # 启动服务端
            self.log("启动Hysteria2服务端...", 'INFO')
            exit_code, _, error = self.server_ssh.execute_command('systemctl restart hysteria2-server')
            if exit_code != 0:
                self.log(f"服务端启动失败: {error}", 'ERROR')
                return False
            
            # 等待服务端启动
            time.sleep(3)
            
            # 启动客户端
            self.log("启动Hysteria2客户端...", 'INFO')
            exit_code, _, error = self.client_ssh.execute_command('systemctl restart hysteria2-client')
            if exit_code != 0:
                self.log(f"客户端启动失败: {error}", 'ERROR')
                return False
        
        elif self.deploy_config['protocol'] == 'quic':
            # 启动服务端
            self.log("启动QUIC服务端...", 'INFO')
            exit_code, _, error = self.server_ssh.execute_command('systemctl restart frp-quic')
            if exit_code != 0:
                self.log(f"服务端启动失败: {error}", 'ERROR')
                return False
        
        self.log("服务启动完成", 'INFO')
        return True
    
    def verify_deployment(self) -> bool:
        """验证部署"""
        self.log("验证部署...", 'STEP')
        
        if self.deploy_config['protocol'] == 'hysteria2':
            # 检查服务端状态
            self.log("检查服务端状态...", 'INFO')
            exit_code, output, _ = self.server_ssh.execute_command('systemctl is-active hysteria2-server')
            if exit_code != 0 or 'active' not in output:
                self.log("服务端未运行", 'ERROR')
                return False
            
            # 检查客户端状态
            self.log("检查客户端状态...", 'INFO')
            exit_code, output, _ = self.client_ssh.execute_command('systemctl is-active hysteria2-client')
            if exit_code != 0 or 'active' not in output:
                self.log("客户端未运行", 'ERROR')
                return False
            
            # 测试连接
            self.log("测试SOCKS5代理连接...", 'INFO')
            test_cmd = f"curl -x socks5://127.0.0.1:{self.deploy_config['hysteria2']['client_local_port']} http://www.baidu.com -I"
            exit_code, output, _ = self.client_ssh.execute_command(test_cmd, timeout=10)
            if exit_code == 0:
                self.log("SOCKS5代理连接测试成功", 'INFO')
            else:
                self.log("SOCKS5代理连接测试失败", 'WARN')
        
        elif self.deploy_config['protocol'] == 'quic':
            # 检查服务端状态
            self.log("检查服务端状态...", 'INFO')
            exit_code, output, _ = self.server_ssh.execute_command('systemctl is-active frp-quic')
            if exit_code != 0 or 'active' not in output:
                self.log("服务端未运行", 'ERROR')
                return False
        
        self.log("部署验证完成", 'INFO')
        return True
    
    def get_logs(self) -> dict:
        """获取服务日志"""
        logs = {
            'client': '',
            'server': ''
        }
        
        if self.deploy_config['protocol'] == 'hysteria2':
            exit_code, output, _ = self.client_ssh.execute_command('journalctl -u hysteria2-client -n 20 --no-pager')
            logs['client'] = output
            
            exit_code, output, _ = self.server_ssh.execute_command('journalctl -u hysteria2-server -n 20 --no-pager')
            logs['server'] = output
        
        elif self.deploy_config['protocol'] == 'quic':
            exit_code, output, _ = self.server_ssh.execute_command('journalctl -u frp-quic -n 20 --no-pager')
            logs['server'] = output
        
        return logs
    
    def save_config(self, path: str = 'deployment_config.json'):
        """保存部署配置"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.deploy_config, f, indent=2, ensure_ascii=False)
        self.log(f"配置已保存到: {path}", 'INFO')
    
    def deploy(self) -> bool:
        """执行完整部署流程"""
        try:
            print("\n" + "="*60)
            print("开始自动化部署")
            print("="*60 + "\n")
            
            # 测试连接
            if not self.test_connections():
                return False
            
            # 准备环境
            if not self.prepare_environment(self.client_ssh, '客户端'):
                return False
            if not self.prepare_environment(self.server_ssh, '服务端'):
                return False
            
            # 根据协议类型安装服务
            if self.deploy_config['protocol'] == 'hysteria2':
                if not self.install_hysteria2_server():
                    return False
                if not self.install_hysteria2_client():
                    return False
            elif self.deploy_config['protocol'] == 'quic':
                if not self.install_quic_server():
                    return False
            
            # 启动服务
            if not self.start_services():
                return False
            
            # 验证部署
            if not self.verify_deployment():
                return False
            
            # 保存配置
            self.save_config()
            
            # 获取日志
            logs = self.get_logs()
            
            print("\n" + "="*60)
            print("部署完成")
            print("="*60 + "\n")
            
            print("服务端日志:")
            print(logs['server'][-500:] if len(logs['server']) > 500 else logs['server'])
            
            if logs['client']:
                print("\n客户端日志:")
                print(logs['client'][-500:] if len(logs['client']) > 500 else logs['client'])
            
            return True
            
        except Exception as e:
            self.log(f"部署失败: {e}", 'ERROR')
            return False
        finally:
            # 关闭连接
            if self.client_ssh:
                self.client_ssh.close()
            if self.server_ssh:
                self.server_ssh.close()


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='FRP服务自动化部署工具')
    parser.add_argument('--protocol', choices=['hysteria2', 'quic'], default='hysteria2',
                        help='选择部署协议 (默认: hysteria2)')
    parser.add_argument('--server-port', type=int, help='服务端端口')
    parser.add_argument('--domain', help='域名（用于Hysteria2证书）')
    parser.add_argument('--config', help='配置文件路径')
    
    args = parser.parse_args()
    
    # 加载配置
    config = DEPLOYMENT_CONFIG.copy()
    if args.config and Path(args.config).exists():
        with open(args.config, 'r', encoding='utf-8') as f:
            config.update(json.load(f))
    
    # 命令行参数覆盖
    config['protocol'] = args.protocol
    if args.server_port:
        if args.protocol == 'hysteria2':
            config['hysteria2']['server_port'] = args.server_port
        else:
            config['quic']['server_port'] = args.server_port
    if args.domain:
        config['hysteria2']['domain'] = args.domain
    
    # 执行部署
    manager = DeploymentManager(CLIENT_SERVER, SERVER_SERVER, config)
    success = manager.deploy()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
