<p>
  <a href="https://github.com/gripsack-dev/gripfetch-conformance/actions/workflows/ci.yml"><img src="https://github.com/gripsack-dev/gripfetch-conformance/actions/workflows/ci.yml/badge.svg" alt="ci"></a>
  <a href="https://pypi.org/project/gripfetch-conformance/"><img src="https://img.shields.io/pypi/v/gripfetch-conformance?label=gripfetch-conformance" alt="PyPI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT"></a>
</p>

# gripfetch-conformance

The protocol contract for `gripfetch-*` transport plugins, made executable.

A gripfetch-* fetcher is a small executable the [gripsack](https://gripsack.dev) core spawns to fetch bytes its built-in fetchers can't reach — internal registries, distro mirrors, mTLS dances. This suite drives your plugin **exactly like the core does** and asserts the contract (plan/0002 §4, 0009 §2):

```
pip install gripfetch-conformance
gripfetch-conformance /path/to/gripfetch-yourplugin
```

## What it checks

| check | contract clause |
|---|---|
| `responds_to_fetch` | one `response` message, on time |
| `stages_bytes_in_dest_dir` | payload lands under `dest_dir` |
| `diagnostics_are_shaped_and_codespaced` | code/severity/message/labels, valid severities |
| `handles_locked` | pinned re-fetch (`locked` present) works — reproduce exactly |
| `reproducible_tree_hash` | same pin, byte-identical trees across runs (no env leakage) |
| `survives_verbose_stderr` | >64KB stderr doesn't deadlock |
| `records_provenance` | which registry/mirror served the bytes (0009 §2 rule 7) |
| `death_is_not_silent` | impossible fetch → error diagnostic or loud stderr exit |

A conformance failure is a bug in the plugin, not an opinion. The full authoring contract lives in the `gripfetch-author` skill (gripsack repo, `.agents/skills/gripfetch-author/SKILL.md`).
