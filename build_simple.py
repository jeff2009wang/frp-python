#!/usr/bin/env python
"""
简化编译脚本 - 不依赖setuptools
直接使用Cython API编译
"""

import sys
import os
import subprocess
from pathlib import Path


def check_dependencies():
    missing = []
    try:
        import Cython
        print(f"✓ Cython {Cython.__version__}")
    except ImportError:
        missing.append("cython")
    
    try:
        from distutils.core import setup, Extension
        from distutils.command.build_ext import build_ext
        print("✓ distutils可用")
    except ImportError:
        missing.append("distutils")
    
    return missing


def install_dependencies(missing):
    print(f"\n正在安装: {', '.join(missing)}")
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            *missing,
            "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("✓ 安装成功")
        return True
    except:
        print("✗ 安装失败")
        return False


def compile_with_cython_api():
    from Cython.Build import cythonize
    from Cython.Compiler import Options
    
    Options.docstrings = False
    Options.fast_fail = True
    
    source_file = Path("frp_core_single.pyx")
    if not source_file.exists():
        print(f"✗ 找不到 {source_file}")
        return False
    
    print("\n正在编译...")
    try:
        extensions = cythonize(
            source_file,
            compiler_directives={
                'language_level': "3",
                'boundscheck': False,
                'wraparound': False,
                'initializedcheck': False,
                'cdivision': True,
                'infer_types': True,
            },
            annotate=False,  # 不生成HTML报告
        )
        
        # 编译成C代码
        print("✓ 生成C代码成功")
        
        # 尝试编译成.so/.pyd
        try:
            from distutils.core import setup, Extension
            from distutils.command.build_ext import build_ext
            
            ext = Extension(
                "frp_core",
                sources=["frp_core_single.c"],
                extra_compile_args=["-O2"],
            )
            
            setup(
                name="frp_core",
                ext_modules=[ext],
                script_args=["build_ext", "--inplace"],
                script_name="setup.py"
            )
            print("✓ 编译二进制文件成功")
            return True
            
        except Exception as e:
            print(f"⚠ 编译二进制失败: {e}")
            print("提示: C代码已生成，但无法编译成.so/.pyd")
            print("可能需要安装C编译器:")
            print("  Windows: Visual Studio Build Tools")
            print("  Linux:   build-essential")
            print("  Mac:     Xcode Command Line Tools")
            return False
            
    except Exception as e:
        print(f"✗ 编译失败: {e}")
        return False


def main():
    print("""
╔══════════════════════════════════════════════╗
║     FRP Core - 简化编译工具                    ║
╚══════════════════════════════════════════════╝
""")
    
    missing = check_dependencies()
    
    if missing:
        print(f"\n缺少依赖: {', '.join(missing)}")
        if not install_dependencies(missing):
            print("\n请手动安装:")
            print(f"  pip install {' '.join(missing)}")
            return False
    
    return compile_with_cython_api()


if __name__ == "__main__":
    try:
        success = main()
        if success:
            print("\n✓ 编译成功！现在可以运行 frpc_quic.py")
        else:
            print("\n使用纯Python版本即可（功能正常）")
    except KeyboardInterrupt:
        print("\n\n已取消")
    except Exception as e:
        print(f"\n错误: {e}")
        print("将使用纯Python版本")
