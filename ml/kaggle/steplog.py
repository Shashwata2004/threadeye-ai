"""Steps of a Kaggle notebook whose log never goes quiet.

``step(name, cmd, limit_min)`` runs a shell command with its output read line by line (unbuffered, time-stamped)
into the notebook log. A heartbeat thread writes a line whenever the log has been silent for a minute (which
step, for how long, machine load, the step's processes and their state), so a slow step and a stuck one can be
told apart from the live log (``kaggle kernels logs -f``). A step that runs past its limit is stopped (SIGINT,
then SIGKILL) and reported as TIMEOUT with its name, instead of using up the session.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from pathlib import Path

T0 = time.time()
HEARTBEAT_S = 60
_lock = threading.Lock()
_last = time.time()
_current: dict = {"name": "start", "since": time.time(), "pid": None}


def log(msg: str) -> None:
    """One time-stamped line in the notebook log."""
    global _last
    with _lock:
        print(f"[{time.time() - T0:6.0f}s] {msg}", flush=True)
        _last = time.time()


def _processes(pid: int | None) -> str:
    """The step's process tree: command, state (R running, S waiting, D waiting on the disk) and CPU %."""
    if pid is None:
        return ""
    try:
        group = os.getpgid(pid)
    except OSError:
        return ""
    out = subprocess.run(["ps", "-o", "pid=,stat=,pcpu=,etime=,args=", "--forest", "-g", str(group)],
                         capture_output=True, text=True, check=False).stdout
    return " | ".join(" ".join(line.split()[:4] + [" ".join(line.split()[4:])[:80]]) for line in out.splitlines()[:6])


def _heartbeat() -> None:
    while True:
        time.sleep(5)
        if time.time() - _last < HEARTBEAT_S:
            continue
        cur = _current
        procs = _processes(cur["pid"])
        load = " ".join(f"{x:.1f}" for x in os.getloadavg())
        log(f"... still in '{cur['name']}' for {(time.time() - cur['since']) / 60:.1f} min, load {load}"
            + (f", processes: {procs}" if procs else ""))


threading.Thread(target=_heartbeat, daemon=True).start()


def phase(name: str) -> None:
    """Name the in-process work that follows (unzipping, linking), for the heartbeat lines."""
    _current.update(name=name, since=time.time(), pid=None)
    log(f"== {name}")


def step(name: str, cmd: str, limit_min: float, cwd: Path | None = None) -> None:
    """Run ``cmd`` (bash, pipefail) as the step ``name``; raise CalledProcessError on failure or timeout."""
    log(f"== {name} (limit {limit_min:g} min): {cmd[:200]}")
    t = time.time()
    p = subprocess.Popen(["bash", "-o", "pipefail", "-c", cmd], cwd=cwd, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1, start_new_session=True,
                         env={**os.environ, "PYTHONUNBUFFERED": "1"})
    _current.update(name=name, since=t, pid=p.pid)

    def read() -> None:
        assert p.stdout is not None
        for line in p.stdout:
            log("   " + line.rstrip()[:400])

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    timed_out = False
    while p.poll() is None:
        if time.time() - t > limit_min * 60:
            timed_out = True
            log(f"!! TIMEOUT: '{name}' still running after {limit_min:g} min; processes: {_processes(p.pid)}")
            os.killpg(p.pid, signal.SIGINT)
            try:
                p.wait(60)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
            break
        time.sleep(1)
    reader.join(10)
    _current.update(name=f"after {name}", since=time.time(), pid=None)
    took = (time.time() - t) / 60
    if timed_out or p.returncode != 0:
        log(f"!! {name}: {'TIMEOUT' if timed_out else f'exit {p.returncode}'} after {took:.1f} min")
        raise subprocess.CalledProcessError(p.returncode if p.returncode else -1, cmd)
    log(f"== {name}: done in {took:.1f} min")
