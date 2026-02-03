import sys
import os
from pathlib import Path


def _get_core_module():
    try:
        from . import frp_core
        return frp_core
    except ImportError:
        from . import frp_core_fallback as frp_core
        return frp_core


core = _get_core_module()

__all__ = ['core', 'create_forwarder']

def create_forwarder(*args, **kwargs):
    return core.create_forwarder(*args, **kwargs)
