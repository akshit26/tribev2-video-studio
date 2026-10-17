"""Read fresh NVIDIA driver telemetry without launching a process per sample."""
import atexit
import ctypes as ct
import os
from functools import lru_cache
from pathlib import Path


class Memory(ct.Structure):
    _fields_ = [('total', ct.c_ulonglong), ('free', ct.c_ulonglong), ('used', ct.c_ulonglong)]


@lru_cache(maxsize=1)
def driver():
    try:
        dll = ct.CDLL(str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'System32/nvml.dll')
                      if os.name == 'nt' else 'libnvidia-ml.so.1')
        signatures = {
            'nvmlInit_v2': [], 'nvmlShutdown': [],
            'nvmlDeviceGetHandleByIndex_v2': [ct.c_uint, ct.POINTER(ct.c_void_p)],
            'nvmlDeviceGetName': [ct.c_void_p, ct.c_char_p, ct.c_uint],
            'nvmlDeviceGetMemoryInfo': [ct.c_void_p, ct.POINTER(Memory)],
            'nvmlDeviceGetTemperature': [ct.c_void_p, ct.c_uint, ct.POINTER(ct.c_uint)],
        }
        for name, args in signatures.items():
            fn = getattr(dll, name); fn.argtypes = args; fn.restype = ct.c_int
        if dll.nvmlInit_v2() != 0: return None
        atexit.register(dll.nvmlShutdown)
        handle = ct.c_void_p()
        if dll.nvmlDeviceGetHandleByIndex_v2(0, ct.byref(handle)) != 0: return None
        return dll, handle
    except (OSError, AttributeError):
        return None


def read_gpu():
    api = driver()
    if api is None: return None
    dll, handle = api
    memory = Memory(); temperature = ct.c_uint(); name = ct.create_string_buffer(128)
    if (dll.nvmlDeviceGetMemoryInfo(handle, ct.byref(memory)) != 0 or
            dll.nvmlDeviceGetTemperature(handle, 0, ct.byref(temperature)) != 0 or
            dll.nvmlDeviceGetName(handle, name, len(name)) != 0):
        return None
    if not memory.total or memory.used > memory.total or not 0 < temperature.value < 150:
        return None
    return {'available': True, 'name': name.value.decode('utf-8', errors='replace'),
            'total_mb': memory.total // 1024**2, 'used_mb': memory.used // 1024**2,
            'temperature_c': temperature.value}
