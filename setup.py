from setuptools import setup, Extension
from Cython.Build import cythonize
import sys

ext_modules = [
    Extension(
        "frp_core",
        ["frp_core.pyx"],
        extra_compile_args=["-O3", "-march=native"],
    )
]

setup(
    name="frp-core",
    ext_modules=cythonize(ext_modules, language_level="3"),
    zip_safe=False,
)
