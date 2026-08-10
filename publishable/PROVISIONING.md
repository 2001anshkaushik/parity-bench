# Provisioning — what a fresh clone does NOT contain, and how to restore it

**A fresh clone is ~2.4 MB. Everything below is excluded deliberately and must be provisioned.**
Each item states why it is not committed and how to get it back.

## 1. The engine bundle (`engine/`, ~1.3 GB)

Vendored binary bundle. Not committed: too large, and it is a released artifact rather than our
source.

```bash
# pinned version and integrity, from publishable/ENVIRONMENT.md
#   server-v3.3.1, reports 3.3.1.35 hash a0817cc6
#   SHA256 846df27ae8b52cd3ed4975124f76462f0cac3ba2e1677a012508247efde6a836
# extract FLAT into benchmark-A/engine/ — the tarball has no top-level dir,
# so --strip-components=1 destroys it
bash working/scripts/start_engine.sh      # ~60 s cold, ~1 s warm
curl -s http://127.0.0.1:5565/version     # health + identity in one call
```

## 2. Benchmark nodes must be copied INTO the bundle

The engine loads nodes from `engine/nodes/`, not from `working/nodes/`. After provisioning the
engine, and after any change to a node:

```bash
cp -R working/nodes/* engine/nodes/ && bash working/scripts/start_engine.sh
```

## 3. ⚠️ pypdf inside the engine's embedded interpreter — NOT manifest-reproducible

**This is a known gap, deliberately not committed, and it must not be.**

`working/nodes/pdf_probe` needs `pypdf` inside the engine's *embedded* CPython 3.12.13. There is
**no documented package-management path** for adding a dependency to that interpreter. It was
installed by copying the package directory in by hand:

```bash
# reproduce the hand-copy (recorded as toil, not endorsed as a deployment method)
python3 -m pip install --target /tmp/pdflibs "pypdf<7"
cp -R /tmp/pdflibs/pypdf        engine/lib/python3.12/site-packages/
cp -R /tmp/pdflibs/pypdf-*.dist-info engine/lib/python3.12/site-packages/
```

**Why this is flagged rather than automated:** it is not reproducible from a manifest, it will not
survive an engine upgrade, and it has to be redone inside any container image. It is recorded as a
RocketRide toil entry in `TOIL_INSTRUMENT.md` and in `PARSER_DECISION.md`. Committing the copied
package would hide the gap and bloat the repo with a vendored dependency.

## 4. The measurement virtualenv

```bash
# Python 3.12.13; see ENVIRONMENT.md for pinned library versions
# key: llama-index-core 0.14.23, sentence-transformers 5.6.1, torch 2.13.0,
#      langchain-text-splitters 1.1.2, pypdf 6.15.0 (BSD-3, see PARSER_DECISION.md)
```

## 5. Corpora (`data/`)

`mt10k` is rebuildable and was verified 10,000/10,000 by sha256 against Leela's manifest:

```python
from sklearn.datasets import fetch_20newsgroups
fetch_20newsgroups(subset="train", remove=(), shuffle=False)
```

## 6. Regenerable working state

`logs/`, `working/pipes/generated/` (2,008 files), `working/results/selftest/`, `pdftest/` are all
produced by the harnesses on demand. Nothing references them as evidence.

---

**Machine-specific values.** No absolute paths are committed; docs use `$REPO` and `$HOME`.
`ROCKETRIDE_APIKEY` defaults to the placeholder `MYAPIKEY` in `start_engine.sh` and is not a
secret. Ports are defaults and overridable by env (`RR_PORT`, `WS1_PORT`).
