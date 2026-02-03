#!/usr/bin/env python3
"""
SSH连接管理器
支持密码和密钥认证，自动化远程命令执行
"""

import paramiko
import logging
from typing import Optional, Tuple, List
import socket

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('SSHManager')


class SSHManager:
    def __init__(self, host: str, port: int, username: str, password: str, key_path: Optional[str] = None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_path = key_path
        self.client = None
    
    def connect(self, timeout: int = 10) -> bool:
        """建立SSH连接"""
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            logger.info(f"正在连接 {self.username}@{self.host}:{self.port}...")
            
            if self.key_path:
                key = paramiko.RSAKey.from_private_key_file(self.key_path)
                self.client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    pkey=key,
                    timeout=timeout
                )
            else:
                self.client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    timeout=timeout
                )
            
            logger.info(f"✓ 成功连接到 {self.host}")
            return True
            
        except socket.timeout:
            logger.error(f"✗ 连接超时: {self.host}:{self.port}")
            return False
        except paramiko.AuthenticationException:
            logger.error(f"✗ 认证失败: {self.host}")
            return False
        except Exception as e:
            logger.error(f"✗ 连接失败: {e}")
            return False
    
    def execute_command(self, command: str, timeout: int = 300) -> Tuple[int, str, str]:
        """执行远程命令"""
        if not self.client:
            return -1, "", "SSH未连接"
        
        try:
            logger.info(f"执行命令: {command[:100]}...")
            stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
            
            exit_status = stdout.channel.recv_exit_status()
            output = stdout.read().decode('utf-8', errors='ignore')
            error = stderr.read().decode('utf-8', errors='ignore')
            
            return exit_status, output, error
            
        except Exception as e:
            logger.error(f"命令执行失败: {e}")
            return -1, "", str(e)
    
    def execute_script(self, script_content: str, script_path: str = '/tmp/deploy_script.sh') -> Tuple[int, str, str]:
        """上传并执行脚本"""
        try:
            # 上传脚本
            sftp = self.client.open_sftp()
            with sftp.file(script_path, 'w') as f:
                f.write(script_content)
            sftp.close()
            
            # 添加执行权限
            self.execute_command(f'chmod +x {script_path}')
            
            # 执行脚本
            return self.execute_command(f'bash {script_path}')
            
        except Exception as e:
            logger.error(f"脚本执行失败: {e}")
            return -1, "", str(e)
    
    def upload_file(self, local_path: str, remote_path: str) -> bool:
        """上传文件到远程服务器"""
        try:
            sftp = self.client.open_sftp()
            sftp.put(local_path, remote_path)
            sftp.close()
            logger.info(f"✓ 文件上传成功: {local_path} -> {remote_path}")
            return True
        except Exception as e:
            logger.error(f"✗ 文件上传失败: {e}")
            return False
    
    def download_file(self, remote_path: str, local_path: str) -> bool:
        """从远程服务器下载文件"""
        try:
            sftp = self.client.open_sftp()
            sftp.get(remote_path, local_path)
            sftp.close()
            logger.info(f"✓ 文件下载成功: {remote_path} -> {local_path}")
            return True
        except Exception as e:
            logger.error(f"✗ 文件下载失败: {e}")
            return False
    
    def upload_directory(self, local_dir: str, remote_dir: str, ignore_patterns: List[str] = None) -> bool:
        """上传整个目录"""
        import os
        from pathlib import Path
        
        try:
            sftp = self.client.open_sftp()
            
            # 创建远程目录
            try:
                sftp.mkdir(remote_dir)
            except IOError:
                pass  # 目录可能已存在
            
            # 上传文件
            local_path = Path(local_dir)
            for file in local_path.rglob('*'):
                if file.is_file():
                    if ignore_patterns and any(pattern in str(file) for pattern in ignore_patterns):
                        continue
                    
                    relative_path = file.relative_to(local_path)
                    remote_file_path = f"{remote_dir}/{relative_path}"
                    
                    # 创建远程子目录
                    remote_file_dir = str(remote_file_path).rsplit('/', 1)[0]
                    try:
                        sftp.makedirs(remote_file_dir)
                    except:
                        pass
                    
                    # 上传文件
                    sftp.put(str(file), remote_file_path)
                    logger.info(f"上传: {file} -> {remote_file_path}")
            
            sftp.close()
            logger.info(f"✓ 目录上传完成: {local_dir} -> {remote_dir}")
            return True
            
        except Exception as e:
            logger.error(f"✗ 目录上传失败: {e}")
            return False
    
    def test_connection(self) -> bool:
        """测试连接是否正常"""
        exit_code, output, _ = self.execute_command('echo "connection_test"')
        return exit_code == 0 and 'connection_test' in output
    
    def get_system_info(self) -> dict:
        """获取系统信息"""
        info = {}
        
        # 系统版本
        exit_code, output, _ = self.execute_command('cat /etc/os-release | grep PRETTY_NAME')
        if exit_code == 0:
            info['os'] = output.strip().split('=')[1].strip('"')
        
        # CPU信息
        exit_code, output, _ = self.execute_command('nproc')
        if exit_code == 0:
            info['cpu_cores'] = output.strip()
        
        # 内存信息
        exit_code, output, _ = self.execute_command('free -h | grep Mem')
        if exit_code == 0:
            info['memory'] = output.strip()
        
        # 磁盘空间
        exit_code, output, _ = self.execute_command('df -h / | tail -1')
        if exit_code == 0:
            info['disk'] = output.strip()
        
        return info
    
    def check_port(self, port: int) -> bool:
        """检查端口是否开放"""
        exit_code, _, error = self.execute_command(f'netstat -tuln | grep {port} || ss -tuln | grep {port}')
        return exit_code == 0
    
    def close(self):
        """关闭连接"""
        if self.client:
            self.client.close()
            logger.info(f"连接已关闭: {self.host}")
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# 预定义的服务器连接
CLIENT_SERVER = {
    'host': '47.117.159.145',
    'port': 9321,
    'username': 'root',  # 根据实际情况修改
    'password': 'uUyb-ARfcT=D2mMpBn(L'
}

SERVER_SERVER = {
    'host': '8.162.10.216',
    'port': 22,
    'username': 'root',  # 根据实际情况修改
    'password': 'JeiFing1234@'
}


def test_both_servers():
    """测试两台服务器的连接"""
    print("\n" + "="*60)
    print("测试服务器连接")
    print("="*60)
    
    # 测试客户端服务器
    print("\n[1/2] 测试客户端服务器...")
    with SSHManager(**CLIENT_SERVER) as client:
        if client.connect():
            print("✓ 客户端服务器连接成功")
            info = client.get_system_info()
            print(f"  系统: {info.get('os', 'Unknown')}")
            print(f"  CPU核心: {info.get('cpu_cores', 'Unknown')}")
            print(f"  内存: {info.get('memory', 'Unknown')}")
        else:
            print("✗ 客户端服务器连接失败")
    
    # 测试服务端服务器
    print("\n[2/2] 测试服务端服务器...")
    with SSHManager(**SERVER_SERVER) as server:
        if server.connect():
            print("✓ 服务端服务器连接成功")
            info = server.get_system_info()
            print(f"  系统: {info.get('os', 'Unknown')}")
            print(f"  CPU核心: {info.get('cpu_cores', 'Unknown')}")
            print(f"  内存: {info.get('memory', 'Unknown')}")
        else:
            print("✗ 服务端服务器连接失败")


if __name__ == "__main__":
    test_both_servers()
