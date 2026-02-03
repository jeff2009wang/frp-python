#!/usr/bin/env python
"""
多Python版本编译脚本
为系统中的所有Python版本编译frp_core
"""

import subprocess
import sys
import os
from pathlib import Path


def find_python_versions():
    """查找系统中所有Python版本"""
    python_versions = []
    
    # Windows可能的路径
    possible_paths = [
        r"C:\Python*\python.exe",
        r"C:\Program Files\Python*\python.exe",
        r"C:\Program Files\Python3*\python.exe",
        r"C:\Users\*\AppData\Local\Programs\Python\Python*\python.exe",
    ]
    
    for pattern in possible_paths:
        for path in Path("/").glob(pattern[1:]):
            if path.exists():
                version = path.parent.name.replace("Python", "").replace(".", "")
                python_versions.append((path, version))
    
    # 去重
    seen = set()
    unique_versions = []
    for path, version in python_versions:
        if version not in seen and version.isdigit():
            seen.add(version)
            unique_versions.append((path, version))
    
    return sorted(unique_versions, key=lambda x: x[1])


def compile_for_version(python_exe, version):
    """为指定Python版本编译"""
    print(f"\n{'='*50}")
    print(f"编译 Python {version}")
    print(f"{'='*50}")
    
    try:
        # 安装依赖
        subprocess.run([
            str(python_exe), "-m", "pip", "install",
            "cython", "setuptools", "-q"
        ], check=True, capture_output=True)
        
        # 编译
        subprocess.run([
            str(python_exe), "setup_single.py",
            "build_ext", "--inplace"
        ], check=True)
        
        # 查找生成的文件
        so_file = list(Path(".").glob(f"frp_core.cp{version}*"))
        if so_file:
            print(f"✓ 生成: {so_file[0].name}")
            return str(so_file[0])
        
    except subprocess.CalledProcessError as e:
        print(f"✗ 失败: {e}")
        return None
    except Exception as e:
        print(f"✗ 错误: {e}")
        return None


def main():
    print("""
╔══════════════════════════════════════════════╗
║     多Python版本编译工具                       ║
╚══════════════════════════════════════════════╝
""")
    
    # 查找所有Python版本
    versions = find_python_versions()
    
    if not versions:
        print("未找到其他Python版本")
        print("当前编译当前Python版本...")
        compile_for_version(sys.executable, ".".join(map(str, sys.version_info[:2])))
        return
    
    print(f"找到 {len(versions)} 个Python版本:")
    for path, version in versions:
        print(f"  - Python {version}: {path}")
    
    compiled_files = []
    
    # 为每个版本编译
    for python_exe, version in versions:
        result = compile_for_version(python_exe, version)
        if result:
            compiled_files.append(result)
    
    # 汇总结果
    print(f"\n{'='*50}")
    print("编译完成")
    print(f"{'='*50}")
    print(f"\n成功编译 {len(compiled_files)} 个版本:")
    for f in compiled_files:
        size = Path(f).stat().st_size / 1024
        print(f"  ✓ {Path(f).name} ({size:.1f} KB)")
    
    print("\n部署提示:")
    print("1. 将对应的 .pyd 文件复制到目标机器")
    print("2. 确保Python版本匹配")
    print("3. 与 .py 文件放在同一目录")


if __name__ == "__main__":
    main()
