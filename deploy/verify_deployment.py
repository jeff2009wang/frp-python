#!/usr/bin/env python3
"""
部署验证脚本
验证服务部署后的连通性和功能
"""

import sys
import time
import socket
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent))
from ssh_manager import SSHManager, CLIENT_SERVER, SERVER_SERVER


class DeploymentVerifier:
    def __init__(self, client_server: dict, server_server: dict, protocol: str = 'hysteria2'):
        self.client_config = client_server
        self.server_config = server_server
        self.protocol = protocol
        self.client_ssh = None
        self.server_ssh = None
    
    def log(self, message: str, status: str = 'INFO'):
        """日志输出"""
        icons = {
            'INFO': '✓',
            'SUCCESS': '✅',
            'ERROR': '✗',
            'WARN': '⚠',
            'STEP': '→',
            'TEST': '🔍'
        }
        icon = icons.get(status, '•')
        print(f"{icon} {message}")
    
    def connect_servers(self) -> bool:
        """连接服务器"""
        self.log("连接服务器...", 'STEP')
        
        try:
            self.client_ssh = SSHManager(**self.client_config)
            if not self.client_ssh.connect():
                self.log("客户端服务器连接失败", 'ERROR')
                return False
            
            self.server_ssh = SSHManager(**self.server_config)
            if not self.server_ssh.connect():
                self.log("服务端服务器连接失败", 'ERROR')
                return False
            
            self.log("服务器连接成功", 'SUCCESS')
            return True
            
        except Exception as e:
            self.log(f"连接失败: {e}", 'ERROR')
            return False
    
    def check_service_status(self) -> dict:
        """检查服务状态"""
        self.log("检查服务状态...", 'STEP')
        
        status = {
            'client': {'running': False, 'enabled': False},
            'server': {'running': False, 'enabled': False}
        }
        
        # 检查客户端服务
        if self.protocol == 'hysteria2':
            exit_code, output, _ = self.client_ssh.execute_command('systemctl is-active hysteria2-client')
            status['client']['running'] = (exit_code == 0 and 'active' in output)
            
            exit_code, output, _ = self.client_ssh.execute_command('systemctl is-enabled hysteria2-client')
            status['client']['enabled'] = (exit_code == 0 and 'enabled' in output)
            
            # 检查服务端
            exit_code, output, _ = self.server_ssh.execute_command('systemctl is-active hysteria2-server')
            status['server']['running'] = (exit_code == 0 and 'active' in output)
            
            exit_code, output, _ = self.server_ssh.execute_command('systemctl is-enabled hysteria2-server')
            status['server']['enabled'] = (exit_code == 0 and 'enabled' in output)
        
        elif self.protocol == 'quic':
            exit_code, output, _ = self.server_ssh.execute_command('systemctl is-active frp-quic')
            status['server']['running'] = (exit_code == 0 and 'active' in output)
            
            exit_code, output, _ = self.server_ssh.execute_command('systemctl is-enabled frp-quic')
            status['server']['enabled'] = (exit_code == 0 and 'enabled' in output)
        
        # 输出结果
        if status['client']['running']:
            self.log("客户端服务: 运行中", 'SUCCESS')
        else:
            self.log("客户端服务: 未运行", 'ERROR')
        
        if status['server']['running']:
            self.log("服务端服务: 运行中", 'SUCCESS')
        else:
            self.log("服务端服务: 未运行", 'ERROR')
        
        return status
    
    def check_port_listening(self) -> dict:
        """检查端口监听状态"""
        self.log("检查端口监听状态...", 'STEP')
        
        ports = {
            'client': [],
            'server': []
        }
        
        # 客户端端口
        exit_code, output, _ = self.client_ssh.execute_command("ss -tuln | grep -E ':(1080|4433|7000)' || netstat -tuln | grep -E ':(1080|4433|7000)'")
        if exit_code == 0:
            for line in output.split('\n'):
                if ':1080' in line:
                    ports['client'].append(1080)
                elif ':4433' in line:
                    ports['client'].append(4433)
        
        # 服务端端口
        exit_code, output, _ = self.server_ssh.execute_command("ss -tuln | grep -E ':(4433|7000)' || netstat -tuln | grep -E ':(4433|7000)'")
        if exit_code == 0:
            for line in output.split('\n'):
                if ':4433' in line:
                    ports['server'].append(4433)
                elif ':7000' in line:
                    ports['server'].append(7000)
        
        # 输出结果
        if ports['client']:
            self.log(f"客户端监听端口: {ports['client']}", 'SUCCESS')
        if ports['server']:
            self.log(f"服务端监听端口: {ports['server']}", 'SUCCESS')
        
        return ports
    
    def test_network_connectivity(self) -> dict:
        """测试网络连通性"""
        self.log("测试网络连通性...", 'STEP')
        
        results = {
            'client_to_server': False,
            'server_to_client': False,
            'internet_access': False
        }
        
        # 测试客户端到服务端的连接
        exit_code, _, _ = self.client_ssh.execute_command(
            f"nc -zv {self.server_config['host']} 4433 2>&1 || "
            f"telnet {self.server_config['host']} 4433 2>&1"
        )
        results['client_to_server'] = (exit_code == 0)
        
        if results['client_to_server']:
            self.log("客户端 → 服务端: 连通", 'SUCCESS')
        else:
            self.log("客户端 → 服务端: 不通", 'ERROR')
        
        # 测试互联网访问
        exit_code, _, _ = self.client_ssh.execute_command('curl -I http://www.baidu.com -s')
        results['internet_access'] = (exit_code == 0)
        
        if results['internet_access']:
            self.log("客户端互联网访问: 正常", 'SUCCESS')
        else:
            self.log("客户端互联网访问: 失败", 'WARN')
        
        return results
    
    def test_socks5_proxy(self) -> bool:
        """测试SOCKS5代理（Hysteria2）"""
        if self.protocol != 'hysteria2':
            return True
        
        self.log("测试SOCKS5代理功能...", 'STEP')
        
        # 测试SOCKS5代理连接
        test_url = 'http://www.baidu.com'
        test_cmd = f'curl -x socks5://127.0.0.1:1080 {test_url} -I -s --connect-timeout 10'
        
        exit_code, output, error = self.client_ssh.execute_command(test_cmd)
        
        if exit_code == 0:
            self.log("SOCKS5代理: 工作正常", 'SUCCESS')
            return True
        else:
            self.log(f"SOCKS5代理: 测试失败 - {error}", 'ERROR')
            return False
    
    def test_quic_connection(self) -> bool:
        """测试QUIC连接"""
        if self.protocol != 'quic':
            return True
        
        self.log("测试QUIC连接...", 'STEP')
        
        # 这里可以添加QUIC连接测试
        # 由于QUIC测试需要专门的客户端，暂时跳过
        self.log("QUIC连接: 需要客户端验证", 'WARN')
        return True
    
    def check_service_logs(self) -> dict:
        """检查服务日志"""
        self.log("检查服务日志...", 'STEP')
        
        logs = {
            'client': '',
            'server': ''
        }
        
        if self.protocol == 'hysteria2':
            exit_code, output, _ = self.client_ssh.execute_command(
                'journalctl -u hysteria2-client -n 50 --no-pager'
            )
            logs['client'] = output
            
            exit_code, output, _ = self.server_ssh.execute_command(
                'journalctl -u hysteria2-server -n 50 --no-pager'
            )
            logs['server'] = output
        
        elif self.protocol == 'quic':
            exit_code, output, _ = self.server_ssh.execute_command(
                'journalctl -u frp-quic -n 50 --no-pager'
            )
            logs['server'] = output
        
        # 检查错误日志
        errors = []
        for log_type, log_content in logs.items():
            if log_content:
                for line in log_content.split('\n'):
                    if 'error' in line.lower() or 'failed' in line.lower():
                        errors.append(f"{log_type}: {line.strip()}")
        
        if errors:
            self.log(f"发现 {len(errors)} 个错误日志", 'WARN')
            for error in errors[:5]:  # 只显示前5个
                self.log(f"  {error}", 'WARN')
        else:
            self.log("未发现错误日志", 'SUCCESS')
        
        return logs
    
    def test_performance(self) -> dict:
        """性能测试"""
        self.log("执行性能测试...", 'STEP')
        
        results = {
            'latency': 0,
            'download_speed': 0,
            'upload_speed': 0
        }
        
        # 延迟测试
        if self.protocol == 'hysteria2':
            # 测试SOCKS5代理延迟
            exit_code, output, _ = self.client_ssh.execute_command(
                'curl -x socks5://127.0.0.1:1080 -w "%{time_total}" -o /dev/null -s http://www.baidu.com'
            )
            if exit_code == 0:
                try:
                    results['latency'] = float(output.strip())
                    self.log(f"延迟: {results['latency']:.3f}s", 'INFO')
                except ValueError:
                    pass
        
        # 下载速度测试
        if self.protocol == 'hysteria2':
            exit_code, output, _ = self.client_ssh.execute_command(
                'curl -x socks5://127.0.0.1:1080 http://speedtest.tele2.net/1MB.zip -o /tmp/test1MB.zip -w "%{speed_download}" -s'
            )
            if exit_code == 0:
                try:
                    speed_bytes = float(output.strip())
                    results['download_speed'] = speed_bytes / 1024  # 转换为KB/s
                    self.log(f"下载速度: {results['download_speed']:.2f} KB/s", 'INFO')
                    
                    # 清理测试文件
                    self.client_ssh.execute_command('rm -f /tmp/test1MB.zip')
                except ValueError:
                    pass
        
        return results
    
    def generate_report(self, status: dict, ports: dict, connectivity: dict,
                        logs: dict, performance: dict) -> str:
        """生成验证报告"""
        report = []
        report.append("\n" + "="*60)
        report.append("部署验证报告")
        report.append("="*60)
        
        # 服务状态
        report.append("\n1. 服务状态")
        report.append(f"   客户端服务: {'✓ 运行中' if status['client']['running'] else '✗ 未运行'}")
        report.append(f"   服务端服务: {'✓ 运行中' if status['server']['running'] else '✗ 未运行'}")
        
        # 端口状态
        report.append("\n2. 端口监听")
        report.append(f"   客户端: {ports['client'] if ports['client'] else '未监听'}")
        report.append(f"   服务端: {ports['server'] if ports['server'] else '未监听'}")
        
        # 网络连通性
        report.append("\n3. 网络连通性")
        report.append(f"   客户端→服务端: {'✓ 通' if connectivity['client_to_server'] else '✗ 不通'}")
        report.append(f"   互联网访问: {'✓ 正常' if connectivity['internet_access'] else '✗ 失败'}")
        
        # 性能指标
        if performance.get('latency', 0) > 0:
            report.append("\n4. 性能指标")
            report.append(f"   延迟: {performance['latency']:.3f}s")
            if performance.get('download_speed', 0) > 0:
                report.append(f"   下载速度: {performance['download_speed']:.2f} KB/s")
        
        # 错误日志摘要
        error_count = 0
        for log_content in logs.values():
            if log_content:
                error_count += log_content.lower().count('error') + log_content.lower().count('failed')
        
        report.append("\n5. 日志状态")
        report.append(f"   错误数量: {error_count}")
        
        if error_count == 0:
            report.append("\n   ✅ 部署验证通过！")
        else:
            report.append("\n   ⚠ 发现问题，请检查日志")
        
        report.append("="*60 + "\n")
        
        return "\n".join(report)
    
    def verify(self) -> bool:
        """执行完整验证流程"""
        try:
            print("\n" + "="*60)
            print("开始部署验证")
            print("="*60 + "\n")
            
            # 连接服务器
            if not self.connect_servers():
                return False
            
            # 检查服务状态
            status = self.check_service_status()
            
            # 检查端口
            ports = self.check_port_listening()
            
            # 测试网络连通性
            connectivity = self.test_network_connectivity()
            
            # 测试协议功能
            if self.protocol == 'hysteria2':
                proxy_ok = self.test_socks5_proxy()
            else:
                proxy_ok = self.test_quic_connection()
            
            # 检查日志
            logs = self.check_service_logs()
            
            # 性能测试
            performance = self.test_performance()
            
            # 生成报告
            report = self.generate_report(status, ports, connectivity, logs, performance)
            print(report)
            
            # 判断验证是否通过
            all_ok = (
                status['server']['running'] and
                connectivity['client_to_server'] and
                proxy_ok
            )
            
            return all_ok
            
        except Exception as e:
            self.log(f"验证失败: {e}", 'ERROR')
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
    
    parser = argparse.ArgumentParser(description='FRP服务部署验证工具')
    parser.add_argument('--protocol', choices=['hysteria2', 'quic'], default='hysteria2',
                        help='验证的协议类型 (默认: hysteria2)')
    
    args = parser.parse_args()
    
    # 执行验证
    verifier = DeploymentVerifier(CLIENT_SERVER, SERVER_SERVER, args.protocol)
    success = verifier.verify()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
