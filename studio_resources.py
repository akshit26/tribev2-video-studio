"""Small resource checks shared by the server and isolated model workers."""
import os

import psutil

START_FREE_MB = 1536
RESERVE_MB = 768
CPU_THREADS = 4
GPU_BUDGET_MB = 4096  # Legacy compatibility value; not a cap. Use maximum_gpu_budget().
GPU_DESKTOP_RESERVE_MB = 512
GPU_GUARD_MB = 256
GPU_PAUSE_C = 76
GPU_STOP_C = 82


class ResourcePressureError(RuntimeError):
    """Stop the job; retrying a model would add more resource pressure."""


def maximum_gpu_budget(total_mb):
    """Total-device target; the runtime guard reserves another 256 MiB within it."""
    return max(0, (int(total_mb) - GPU_DESKTOP_RESERVE_MB) // 256 * 256)


def memory_info():
    memory = psutil.virtual_memory()
    return {"available_mb": int(memory.available / 1024**2),
            "total_mb": int(memory.total / 1024**2)}


def require_memory(minimum_mb=START_FREE_MB):
    available = memory_info()["available_mb"]
    if available < minimum_mb:
        raise ResourcePressureError(
            f"Analysis stopped to keep Windows responsive: only {available / 1024:.1f} GB "
            f"RAM is available (requires {minimum_mb / 1024:.1f} GB). "
            "Close unused apps, then use Resume saved analysis for the existing video.")


def limit_cpu_threads():
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                 "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ[name] = str(CPU_THREADS)
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
