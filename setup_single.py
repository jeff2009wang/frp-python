#!/usr/bin/env python
# 单文件编译脚本

from setuptools import setup, Extension
from Cython.Build import cythonize
import sys
import os

ext = Extension(
    "frp_core",  # 编译后的模块名
    sources=["frp_core_single.pyx"],
    extra_compile_args=["-O3"],  # 最高优化级别
)

setup(
    name="frp-core",
    ext_modules=cythonize([ext], language_level="3"),
    zip_safe=False,
)
