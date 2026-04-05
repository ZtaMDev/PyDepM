from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Sequence


TickCallback = Callable[[], None]


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str


def run_with_ticks(
    args: Sequence[str],
    *,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
    tick: Optional[TickCallback] = None,
    tick_interval_seconds: float = 0.1,
) -> RunResult:
    """Run a subprocess while optionally emitting periodic tick callbacks.

    This is used by the CLI to drive progress bars while an external tool runs.
    """

    proc = subprocess.Popen(
        list(args),
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout_parts: list[str] = []
    stderr_parts: list[str] = []

    def _drain(stream, sink: list[str]) -> None:
        try:
            for line in stream:
                sink.append(line)
        finally:
            try:
                stream.close()
            except Exception:
                pass

    t_out = threading.Thread(target=_drain, args=(proc.stdout, stdout_parts), daemon=True)
    t_err = threading.Thread(target=_drain, args=(proc.stderr, stderr_parts), daemon=True)
    t_out.start()
    t_err.start()

    while proc.poll() is None:
        if tick is not None:
            tick()
        time.sleep(tick_interval_seconds)

    t_out.join(timeout=1)
    t_err.join(timeout=1)

    return RunResult(
        returncode=proc.returncode or 0,
        stdout="".join(stdout_parts),
        stderr="".join(stderr_parts),
    )
