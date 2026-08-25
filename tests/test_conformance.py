"""Self-tests: the suite must pass a conforming plugin and catch each
class of violation."""

from pathlib import Path

from gripfetch_conformance.main import CHECKS

FIXTURES = Path(__file__).parent / "fixtures"


def run_all(exe):
    results = {}
    for name, fn in CHECKS.items():
        try:
            fn(exe)
            results[name] = True
        except AssertionError:
            results[name] = False
    return results


def test_good_plugin_passes_everything():
    results = run_all(str(FIXTURES / "gripfetch-good")
)
    assert all(results.values()), [k for k, v in results.items() if not v]


def test_silent_death_is_caught():
    results = run_all(str(FIXTURES / "gripfetch-silent"))
    assert results["death_is_not_silent"] is False


def test_nondeterminism_is_caught():
    results = run_all(str(FIXTURES / "gripfetch-nondeterministic"))
    assert results["reproducible_tree_hash"] is False
