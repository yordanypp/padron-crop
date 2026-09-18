"""Autotune adaptativo: la maquina decide cuantos workers usar.

- Servidor potente (muchos nucleos + RAM libre) -> aprovecha al maximo.
- PC vieja o con poca RAM -> pocos workers, sin tumbar la maquina.
- Regla: workers=0 (o sin flag) = automatico. Un numero explicito o la
  variable PADRON_WORKERS siempre mandan sobre el automatico.

Solo libreria estandar: CPU via os.cpu_count, RAM via ctypes en Windows
(GlobalMemoryStatusEx) o sysconf en POSIX; si nada responde, asume
maquina modesta (2 GB) para no prometer de mas.
"""
from __future__ import annotations

import os

# Presupuesto por worker: con imagenes de padron tipicas (<5 MP) un worker
# rara vez pasa de 300 MB; se reserva 750 MB para cubrir fotos pesadas.
BYTES_PER_WORKER = int(os.environ.get("PADRON_BYTES_PER_WORKER", 750 * 1024 * 1024))


def _ram_gb() -> tuple[float, float]:
    """(total_gb, free_gb). Fallback conservador si no se puede medir."""
    try:
        import ctypes

        class _MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        ms = _MS()
        ms.dwLength = ctypes.sizeof(_MS)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
            g = 1024 ** 3
            return ms.ullTotalPhys / g, ms.ullAvailPhys / g
    except Exception:
        pass
    try:
        if os.name == "posix" and hasattr(os, "sysconf"):
            pages = os.sysconf("SC_PHYS_PAGES")
            avail = os.sysconf("SC_AVPHYS_PAGES")
            size = os.sysconf("SC_PAGE_SIZE")
            g = 1024 ** 3
            return pages * size / g, avail * size / g
    except Exception:
        pass
    return 2.0, 1.0  # modesta por defecto: no prometer de mas


def machine_profile() -> dict:
    """CPU y RAM detectados en esta maquina."""
    total, free = _ram_gb()
    return {"cpu": max(1, os.cpu_count() or 1),
            "ram_gb": round(total, 2),
            "free_gb": round(free, 2)}


def recommend_workers(profile: dict | None = None) -> int:
    """Workers optimos: min(nucleos, lo que cabe en la RAM libre).

    Se usa como maximo el 75% de la RAM libre para dejar aire al SO.
    Minimo garantizado: 1 (maquina muy debil igual trabaja, solo mas lento).
    """
    p = profile or machine_profile()
    cpu = max(1, int(p.get("cpu", 1)))
    free_bytes = max(0.0, float(p.get("free_gb", 1.0))) * (1024 ** 3)
    by_ram = int((free_bytes * 0.75) // BYTES_PER_WORKER)
    return max(1, min(cpu, by_ram))


def effective_workers(requested: int | None) -> int:
    """Resuelve workers finales: explicito > env > auto(0/None)."""
    if requested and int(requested) >= 1:
        return int(requested)
    env = os.environ.get("PADRON_WORKERS")
    if env:
        try:
            if int(env) >= 1:
                return int(env)
        except ValueError:
            pass
    return recommend_workers()


def describe() -> str:
    """Linea legible para logs y EDA: 'auto: 6 workers (8 nucleos, 5.2 GB libres)'."""
    p = machine_profile()
    return (f"auto: {recommend_workers(p)} workers "
            f"({p['cpu']} nucleos, {p['free_gb']} GB libres)")
