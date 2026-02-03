#!/usr/bin/env python
"""
部署检查脚本 - 检查Python版本和编译模块是否匹配
"""

import sys
from pathlib import Path


def get_python_version():
    """获取Python版本号"""
    return f"{sys.version_info.major}{sys.version_info.minor}"


def get_soa_module():
    """查找编译的模块文件"""
    current_dir = Path(".")
    
    if sys.platform == "win32":
        so_files = list(current_dir.glob("frp_core.cp*.pyd"))
    else:
        so_files = list(current_dir.glob("frp_core.cp*.so"))
    
    return so_files


def check_compatibility():
    """检查版本兼容性"""
    py_version = get_python_version()
    print(f"当前Python版本: 3.{py_version[1]}.{sys.version_info.micro}")
    print(f"版本代号: cp{py_version}")
    
    so_files = get_soa_module()
    
    if not so_files:
        print("\n⚠ 未找到编译模块")
        print("建议运行: python build_core.py")
        return False
    
    print(f"\n找到 {len(so_files)} 个编译模块:")
    
    compatible = False
    for so_file in so_files:
        size = so_file.stat().st_size / 1024
        print(f"  - {so_file.name} ({size:.1f} KB)")
        
        # 检查是否匹配
        if f"cp{py_version}" in so_file.name:
            compatible = True
            print(f"    ✓ 匹配当前Python版本！")
        else:
            print(f"    ✗ 不匹配 (需要 cp{py_version})")
    
    if compatible:
        print("\n✓ 可以使用Cython加速版本")
        return True
    else:
        print(f"\n✗ 没有匹配Python 3.{py_version[1]}的编译模块")
        print("\n解决方法:")
        print(f"1. 运行: python build_core.py")
        print(f"2. 或使用纯Python版本（性能略低）")
        return False


def show_deployment_info():
    """显示部署信息"""
    print("\n" + "="*50)
    print("部署信息")
    print("="*50)
    print("\n如果部署到其他机器:")
    print("1. 确认目标机器的Python版本")
    print("2. 编译对应版本的模块:")
    print("   python build_core.py")
    print("3. 复制文件:")
    if sys.platform == "win32":
        print("   - frpc_quic.py")
        print("   - frps_quic.py")
        print("   - frp_core.cp**.pyd")
    else:
        print("   - frpc_quic.py")
        print("   - frps_quic.py")
        print("   - frp_core.cp**.so")
    print("4. 如果版本不匹配，会自动回退纯Python版本")


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════╗
║     Python版本兼容性检查工具                   ║
╚══════════════════════════════════════════════╝
""")
    
    if check_compatibility():
        print("\n✓ 系统配置正确，可以运行！")
    
    show_deployment_info()
