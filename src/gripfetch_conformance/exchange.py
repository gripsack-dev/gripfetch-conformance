"""Drive a gripfetch-* plugin the way the core does (plan/0002 §4).

One JSON request on stdin, NDJSON messages on stdout, stderr drained
concurrently, exchange deadline. The conformance suite asserts the
plugin's side of the contract against this host.
"""

from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

TIMEOUT_S = 60


@dataclass
class Exchange:
    """The captured result of one fetch exchange."""

    status: Optional[int]
    messages: list[dict[str, Any]] = field(default_factory=list)
    stderr_tail: str = ""
    timed_out: bool = False

    @property
    def responses(self) -> list[dict[str, Any]]:
        return [m for m in self.messages if m.get("type") == "response"]

    @property
    def diagnostics(self) -> list[dict[str, Any]]:
        return [m["diagnostic"] for m in self.messages if m.get("type") == "diagnostic"]


def run_exchange(
    exe: str,
    dest: Path,
    *,
    args: Optional[dict] = None,
    locked: Optional[dict] = None,
    stdin_extra: str = "",
    timeout: int = TIMEOUT_S,
) -> Exchange:
    """Spawn the plugin with one request and capture the exchange."""
    request: dict[str, Any] = {
        "op": "fetch",
        "args": args if args is not None else {"package": "conformance-probe", "version": "1.0.0"},
        "dest_dir": str(dest),
    }
    if locked is not None:
        request["locked"] = locked

    child = subprocess.Popen(
        [exe],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert child.stdin and child.stdout and child.stderr
    child.stdin.write(json.dumps(request) + "\n" + stdin_extra)
    child.stdin.close()

    stderr_buf: list[str] = []

    def drain() -> None:
        assert child.stderr is not None
        for chunk in child.stderr:
            if sum(map(len, stderr_buf)) < 256 * 1024:
                stderr_buf.append(chunk)

    drainer = threading.Thread(target=drain, daemon=True)
    drainer.start()

    exchange = Exchange(status=None)
    try:
        for line in child.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                exchange.messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # tolerance: non-protocol lines are ignored (0009)
        child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()
        exchange.timed_out = True
    drainer.join(timeout=5)
    exchange.status = child.returncode
    exchange.stderr_tail = "".join(stderr_buf)[-2000:]
    return exchange


def tree_hash(dest: Path) -> str:
    """Canonical tree identity, mirrors the core's canonical_tree_hash."""
    import hashlib

    entries: list[str] = []
    for path in sorted(dest.rglob("*")):
        rel = path.relative_to(dest).as_posix()
        if path.is_symlink():
            entries.append(f"L{rel}\0{path.readlink()}")
        elif path.is_file():
            entries.append(f"F{rel}\0{hashlib.sha256(path.read_bytes()).hexdigest()}")
        else:
            entries.append(f"D{rel}\0")
    return hashlib.sha256("\n".join(entries).encode()).hexdigest()
