#!/usr/bin/env python
"""
一键编译脚本 - 单文件版本
运行此脚本编译Cython模块，性能提升50-100%
"""

import subprocess
import sys
import os
from pathlib import Path


def check_cython():
    try:
        import Cython
        print(f"✓ Cython版本: {Cython.__version__}")
        return True
    except ImportError:
        print("✗ Cython未安装")
        return False


def install_cython():
    print("\n正在安装Cython和setuptools...")
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", 
            "cython", "setuptools", "wheel",
            "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"  # 国内镜像
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("✓ Cython和setuptools安装成功")
        return True
    except subprocess.CalledProcessError:
        print("✗ 依赖安装失败")
        return False


def build_core():
    print("\n" + "="*50)
    print("开始编译 frp_core...")
    print("="*50)
    
    if not check_cython():
        print("\n是否自动安装Cython并编译? [Y/n]: ", end="")
        try:
            choice = input().lower()
        except EOFError:
            choice = 'y'
        
        if choice != 'n':
            if not install_cython():
                print("\n跳过编译，将使用纯Python版本")
                return False
        else:
            print("跳过编译，将使用纯Python版本")
            return False
    
    try:
        print("\n正在编译...")
        subprocess.check_call([
            sys.executable, "setup_single.py",
            "build_ext", "--inplace"
        ])
        
        print("\n" + "="*50)
        print("✓ 编译成功！")
        print("="*50)
        
        if os.name == 'nt':
            so_file = list(Path(".").glob("frp_core*.pyd"))
        else:
            so_file = list(Path(".").glob("frp_core*.so"))
        
        if so_file:
            print(f"\n生成的文件: {so_file[0].name}")
            print(f"文件大小: {so_file[0].stat().st_size / 1024:.1f} KB")
        
        if os.path.exists("frp_core.c"):
            print("\n提示: 可以删除 frp_core.c 以节省空间")
            print("命令: rm frp_core.c  (Linux/Mac)")
            print("      del frp_core.c (Windows)")
        
        print("\n现在运行 frpc_quic.py 将自动使用加速版本！")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"\n✗ 编译失败: {e}")
        print("\n可能的原因:")
        print("1. 缺少C编译器")
        print("   Windows: 安装 Visual Studio Build Tools")
        print("   Linux:   sudo apt install build-essential")
        print("   Mac:     xcode-select --install")
        print("\n2. 将使用纯Python版本（性能略低）")
        return False
    except KeyboardInterrupt:
        print("\n\n编译已取消")
        return False


def test_compiled():
    print("\n" + "="*50)
    print("测试编译模块...")
    print("="*50)
    
    try:
        import frp_core
        print("✓ 模块导入成功")
        
        # 测试性能
        if hasattr(frp_core, 'run_performance_test'):
            print("\n运行性能测试...")
            frp_core.run_performance_test()
        
        return True
    except ImportError as e:
        print(f"✗ 模块导入失败: {e}")
        return False


def show_info():
    print("\n" + "="*50)
    print("编译信息")
    print("="*50)
    print(f"Python版本: {sys.version}")
    print(f"操作系统: {os.name}")
    print(f"架构: {sys.platform}")
    
    if os.name == 'nt':
        print("\nWindows编译产物: frp_core.cp*.pyd")
    else:
        print("\nUnix编译产物: frp_core.cp*.so")


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════╗
║     FRP Core - Cython加速模块编译工具         ║
╚══════════════════════════════════════════════╝
    """)
    
    show_info()
    
    if build_core():
        test_compiled()
        
        print("\n" + "="*50)
        print("部署说明")
        print("="*50)
        print("1. 本机运行: 自动使用加速版")
        print("2. 部署到其他机器:")
        if os.name == 'nt':
            print("   - 复制 frp_core*.pyd 文件")
        else:
            print("   - 复制 frp_core*.so 文件")
        print("   - 与 .py 文件放在同一目录")
        print("\n3. 如果没有编译文件:")
        print("   - 自动回退到纯Python版本")
        print("   - 功能完全相同，性能略低")
    else:
        print("\n使用纯Python版本运行")
        print("功能完全正常，无需担心！")
    
    print("\n" + "="*50)
