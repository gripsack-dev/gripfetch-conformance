"""The conformance suite (plan/0002 §4, 0009 §2): every check is a
contract clause, named. A failure means the plugin, not the protocol."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from .exchange import run_exchange, tree_hash

CHECKS = {}


def check(fn):
    CHECKS[fn.__name__] = fn
    return fn


def _args():
    return {"package": "conformance-probe", "version": "1.0.0"}


@check
def responds_to_fetch(exe: str) -> str:
    """The exchange ends with exactly one response message."""
    with tempfile.TemporaryDirectory() as td:
        ex = run_exchange(exe, Path(td))
    assert not ex.timed_out, "exchange exceeded the deadline"
    assert ex.responses, "no response message — death is not silent?"
    assert len(ex.responses) == 1, f"expected one response, got {len(ex.responses)}"
    return "one response, on time"


@check
def declares_capabilities(exe: str) -> str:
    """The `capabilities` op (0002 §throttle): the fetcher answers
    with its declared rate budgets — or, if it predates the op, fails
    tolerantly (the core treats that as "no declared budgets")."""
    with tempfile.TemporaryDirectory() as td:
        ex = run_exchange(exe, Path(td), op="capabilities")
    assert not ex.timed_out, "capabilities exchange exceeded the deadline"
    if not ex.responses:
        # tolerated: an older plugin may not know the op — but it must
        # still die noisily (non-zero exit or an error diagnostic)
        assert ex.status != 0 or any(
            d.get("severity") == "error" for d in ex.diagnostics
        ), "unknown op must not look like success"
        return "pre-capabilities plugin (tolerated)"
    caps = ex.responses[0].get("result", {}).get("capabilities", {})
    throttle = caps.get("throttle", {})
    assert isinstance(throttle, dict), "capabilities.throttle must be a map"
    for domain, budget in throttle.items():
        assert "/" in str(budget), f"budget for {domain} must look like N/unit"
    return f"{len(throttle)} budget(s) declared"

@check
def stages_bytes_in_dest_dir(exe: str) -> str:
    """The plugin writes its payload under dest_dir. A plugin that
    cannot resolve the conformance probe answers with an error
    diagnostic (the honest shape) and MAY stage only a note; a plugin
    answering success must stage real bytes (gripfetch-apt review)."""
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td)
        ex = run_exchange(exe, dest)
        staged = list(dest.rglob("*"))
    assert ex.responses, "no response"
    errored = any(d.get("severity") == "error" for d in ex.diagnostics)
    if errored:
        return "unresolvable probe answered with an error diagnostic (honest)"
    assert staged, "success with an empty dest_dir is a fabricated payload"
    return f"staged {len(staged)} entries"


@check
def diagnostics_are_shaped_and_codespaced(exe: str) -> str:
    """Diagnostics carry code/severity/message/labels; codes look
    like plugin codes (bare or already namespaced)."""
    with tempfile.TemporaryDirectory() as td:
        ex = run_exchange(exe, Path(td))
    for d in ex.diagnostics:
        for field in ("code", "severity", "message", "labels"):
            assert field in d, f"diagnostic missing {field!r}: {d}"
        assert d["severity"] in ("error", "warning"), f"bad severity: {d['severity']}"
        assert isinstance(d["labels"], list), "labels must be a list"
    return f"{len(ex.diagnostics)} diagnostic(s) well-formed"


@check
def handles_locked(exe: str) -> str:
    """A pinned re-fetch (locked present) succeeds — reproduce exactly
    is a different code path, and it must exist."""
    locked = {"url": "https://registry.invalid/a/1.0.0.tgz", "version": "1.0.0", "sha256": "0" * 64}
    with tempfile.TemporaryDirectory() as td:
        ex = run_exchange(exe, Path(td), locked=locked)
    assert not ex.timed_out, "locked exchange exceeded the deadline"
    assert ex.responses, "no response to a locked request"
    return "locked accepted"


@check
def reproducible_tree_hash(exe: str) -> str:
    """Same pin, two runs, byte-identical trees — absolute paths,
    timestamps, and ordering must not leak into the payload."""
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        run_exchange(exe, Path(a))
        run_exchange(exe, Path(b))
        ha, hb = tree_hash(Path(a)), tree_hash(Path(b))
    assert ha == hb, f"tree hashes differ across runs: {ha[:12]}… vs {hb[:12]}…"
    return f"stable hash {ha[:12]}…"


@check
def survives_verbose_stderr(exe: str) -> str:
    """>64KB of stderr chatter must not deadlock the exchange."""
    with tempfile.TemporaryDirectory() as td:
        ex = run_exchange(
            exe,
            Path(td),
            args={**_args(), "verbose_stderr_lines": 4000},
        )
    assert not ex.timed_out, "exchange hung on verbose stderr"
    assert ex.responses, "no response after verbose stderr"
    return "64KB+ stderr drained"


@check
def records_provenance(exe: str) -> str:
    """The response carries provenance — registry, mirror, identity
    (0009 §2 rule 7: it lands in the run log)."""
    with tempfile.TemporaryDirectory() as td:
        ex = run_exchange(exe, Path(td))
    results = [m.get("result") or {} for m in ex.responses]
    assert any(r.get("provenance") for r in results), (
        "no provenance in the response — which registry served the bytes?"
    )
    return "provenance recorded"


@check
def death_is_not_silent(exe: str) -> str:
    """Asked for the impossible, the plugin emits an error diagnostic
    or exits nonzero with a useful stderr tail."""
    with tempfile.TemporaryDirectory() as td:
        ex = run_exchange(exe, Path(td), args={"package": "does-not-exist-404", "version": "0.0.0"})
    errors = [d for d in ex.diagnostics if d.get("severity") == "error"]
    died_loudly = ex.status not in (0, None) and ex.stderr_tail.strip()
    assert errors or died_loudly, (
        "impossible fetch answered success — fabricating a payload for "
        "does-not-exist-404 is a lie, not a result (error diagnostic or "
        "nonzero exit, always)"
    )
    return "failure is loud, success is never fabricated"


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: gripfetch-conformance /path/to/gripfetch-<name>")
        raise SystemExit(2)
    exe = sys.argv[1]
    failures = 0
    for name, fn in CHECKS.items():
        try:
            note = fn(exe)
            print(f"  ✓ {name}: {note}")
        except AssertionError as e:
            failures += 1
            print(f"  ✗ {name}: {e}")
        except Exception as e:  # noqa: BLE001 — the plugin's crash is a conformance failure
            failures += 1
            print(f"  ✗ {name}: plugin crashed — {e}")
    print(f"\n{len(CHECKS) - failures}/{len(CHECKS)} checks passed")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
