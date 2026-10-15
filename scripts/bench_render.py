#!/usr/bin/env python3
"""
Mide RAM y CPU de un render (HG) — pensado para correr DENTRO de Docker.

Lanza el comando (o N copias en paralelo con --jobs) y cada 0.25 s suma, de
todo el árbol de procesos (Python + Manim + FFmpeg + LaTeX):
  - RSS (memoria residente real, sin caché de disco),
  - tiempo de CPU (utime + stime) → núcleos usados en promedio y en el pico.
Si el proceso corre en un contenedor también reporta el pico de memoria del
cgroup (incluye caché de páginas; es lo que compara el límite `mem_limit`) y
si el kernel mató algo por falta de memoria (OOM).

Ejemplos (desde la raíz del repo):
  python scripts/bench_render.py -- python scripts/render_video2_scenes.py examples/video2_manim.yaml --only V2E07_CadenaCompleta --draft --no-cache
  python scripts/bench_render.py --jobs 2 --label "2 overlays 1080p" -- python scripts/render_manim_clips.py --scene Scene02Math --output data/renders/bench/{job}.mov --no-cache

  docker compose run --rm video-app python scripts/bench_render.py --json data/renders/bench.jsonl -- \\
      python -m src.video_automation.cli render --script examples/episodio3_overlays.yaml --no-audio --draft

En el comando, {job} se reemplaza por el número de copia (0, 1, ...) para que
las copias paralelas no escriban el mismo archivo.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
INTERVAL = 0.25


def _children_map() -> Dict[int, List[int]]:
    kids: Dict[int, List[int]] = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/stat", "rb") as fh:
                parts = fh.read().rsplit(b")", 1)[1].split()
            kids.setdefault(int(parts[1]), []).append(int(d))
        except (OSError, IndexError, ValueError):
            continue
    return kids


def _tree(roots: Sequence[int]) -> List[int]:
    kids, out, stack = _children_map(), [], list(roots)
    while stack:
        p = stack.pop()
        out.append(p)
        stack.extend(kids.get(p, []))
    return out


def _proc_sample(pid: int):
    """(rss_bytes, cpu_seconds) de un proceso; (0, 0) si ya terminó."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as fh:
            parts = fh.read().rsplit(b")", 1)[1].split()
        cpu = (int(parts[11]) + int(parts[12])) / CLK_TCK   # utime + stime
        rss = int(parts[21]) * PAGE
        return rss, cpu
    except (OSError, IndexError, ValueError):
        return 0, 0.0


def _cgroup_file(*names: str) -> Optional[Path]:
    for n in names:
        p = Path(n)
        if p.is_file():
            return p
    return None


def cgroup_peak_bytes() -> Optional[int]:
    """Pico de memoria del cgroup (v2 memory.peak o v1 max_usage_in_bytes)."""
    f = _cgroup_file("/sys/fs/cgroup/memory.peak", "/sys/fs/cgroup/memory/memory.max_usage_in_bytes")
    try:
        return int(f.read_text().strip()) if f else None
    except (OSError, ValueError):
        return None


def cgroup_limit_bytes() -> Optional[int]:
    f = _cgroup_file("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes")
    try:
        raw = f.read_text().strip() if f else ""
        val = int(raw) if raw and raw != "max" else None
        return val if val and val < (1 << 60) else None
    except (OSError, ValueError):
        return None


def cgroup_oom_kills() -> Optional[int]:
    f = _cgroup_file("/sys/fs/cgroup/memory.events", "/sys/fs/cgroup/memory/memory.oom_control")
    if not f:
        return None
    try:
        for line in f.read_text().splitlines():
            k, _, v = line.partition(" ")
            if k == "oom_kill":
                return int(v)
    except (OSError, ValueError):
        return None
    return None


def cpu_quota() -> Optional[float]:
    """Núcleos permitidos por el contenedor (cpus: en compose); None = sin límite."""
    v2 = Path("/sys/fs/cgroup/cpu.max")
    try:
        if v2.is_file():
            q, p = v2.read_text().split()
            return None if q == "max" else int(q) / int(p)
        q = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
        p = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
        if q.is_file() and p.is_file():
            qv = int(q.read_text())
            return None if qv <= 0 else qv / int(p.read_text())
    except (OSError, ValueError):
        return None
    return None


def run(cmd: Sequence[str], jobs: int, env: Optional[Dict[str, str]] = None) -> Dict:
    oom0 = cgroup_oom_kills() or 0
    t0 = time.monotonic()
    # La salida va a archivos, NO a un pipe: MoviePy/Manim escriben mucho en
    # stderr y un pipe sin leer (64 KB) bloquea el render para siempre.
    logs = [tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") for _ in range(jobs)]
    procs = [subprocess.Popen([c.replace("{job}", str(i)) for c in cmd], env=env,
                              stdout=logs[i], stderr=subprocess.STDOUT)
             for i in range(jobs)]
    roots = [p.pid for p in procs]
    peak_rss, last_cpu_total, last_t = 0, 0.0, t0
    seen_cpu: Dict[int, float] = {}
    peak_cores = 0.0
    while any(p.poll() is None for p in procs):
        time.sleep(INTERVAL)
        rss = 0
        for pid in _tree(roots):
            r, c = _proc_sample(pid)
            rss += r
            if c:
                seen_cpu[pid] = c          # CPU acumulado del proceso (sobrevive si muere)
        cpu_total = sum(seen_cpu.values())
        now = time.monotonic()
        if now > last_t:
            peak_cores = max(peak_cores, (cpu_total - last_cpu_total) / (now - last_t))
        last_cpu_total, last_t = cpu_total, now
        peak_rss = max(peak_rss, rss)
    wall = time.monotonic() - t0
    errors = []
    for p, log in zip(procs, logs):
        if p.returncode != 0:
            log.seek(0)
            errors.append(log.read()[-1500:])
        log.close()
    cpu_total = sum(seen_cpu.values())
    oom1 = cgroup_oom_kills()
    return {
        "jobs": jobs,
        "wall_s": round(wall, 2),
        "peak_rss_mb": round(peak_rss / 2**20),
        "cgroup_peak_mb": (round(cgroup_peak_bytes() / 2**20) if cgroup_peak_bytes() else None),
        "mem_limit_mb": (round(cgroup_limit_bytes() / 2**20) if cgroup_limit_bytes() else None),
        "cpu_s": round(cpu_total, 1),
        "avg_cores": round(cpu_total / wall, 2) if wall else 0.0,
        "peak_cores": round(peak_cores, 2),
        "cpu_quota": cpu_quota(),
        "oom_kills": (oom1 - oom0) if oom1 is not None else None,
        "exit_codes": [p.returncode for p in procs],
        "errors": errors,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):   # Windows + pipe: cp1252 truena con 📊/❌
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", type=int, default=1, help="Copias del comando en paralelo")
    ap.add_argument("--label", default="", help="Nombre de la medición (para la tabla)")
    ap.add_argument("--json", type=Path, help="Agrega el resultado como una línea JSON a este archivo")
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="-- comando a medir")
    args = ap.parse_args(argv)
    cmd = args.cmd[1:] if args.cmd[:1] == ["--"] else args.cmd
    if not cmd:
        ap.error("falta el comando: bench_render.py [opciones] -- <comando>")
    if args.jobs < 1:
        ap.error("--jobs debe ser >= 1")

    res = run(cmd, args.jobs)
    res["label"] = args.label or " ".join(cmd)[:80]
    lim = f" / límite {res['mem_limit_mb']} MB" if res["mem_limit_mb"] else ""
    quota = f" (cuota {res['cpu_quota']:.1f})" if res["cpu_quota"] else ""
    print(f"📊 {res['label']}\n"
          f"   jobs={res['jobs']}  tiempo={res['wall_s']} s  RSS pico={res['peak_rss_mb']} MB"
          f"  cgroup pico={res['cgroup_peak_mb']} MB{lim}\n"
          f"   CPU={res['cpu_s']} s  núcleos prom={res['avg_cores']}  pico={res['peak_cores']}{quota}"
          f"  OOM={res['oom_kills']}  salida={res['exit_codes']}")
    for e in res["errors"]:
        tail = [ln for ln in e.strip().splitlines() if ln.strip()][-6:]
        print("   ❌ " + ("\n      ".join(tail) if tail else "sin salida"))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        with args.json.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(res, ensure_ascii=False) + "\n")
    return 0 if all(c == 0 for c in res["exit_codes"]) else 1


if __name__ == "__main__":
    sys.exit(main())
