# Provisioning — what a fresh clone does NOT contain, and how to restore it

**A fresh clone is ~4.2 MB (338 files). Everything below is excluded deliberately and must be
provisioned.** Provisioned in full it is ~7.1 GB, almost all of it the engine bundle and the corpus.
Each item states why it is not committed and how to get it back.

## 1. The engine bundle (`engine/`, ~1.3 GB)

Vendored binary bundle. Not committed: too large, and it is a released artifact rather than our
source.

```bash
# pinned version and integrity, from publishable/ENVIRONMENT.md
#   server-v3.3.1, reports 3.3.1.35 hash a0817cc6
#   SHA256 846df27ae8b52cd3ed4975124f76462f0cac3ba2e1677a012508247efde6a836
# extract FLAT into <clone>/engine/ — the tarball has no top-level dir,
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

**If your clone is not named `benchmark-A`, set `RR_NODE_MARK`.** The harnesses find the engine's
per-task node processes by matching a literal substring against process command lines, and the
default contains the directory the clone sits in:

```bash
export RR_NODE_MARK='engine/ai/node.py'      # directory-independent; only needed if renamed
```

The default is `benchmark-A/engine/ai/node.py`, defined once in `working/harness/engine_ops.py` and
used by `fault_matrix.py`, `model_a_bisect.py`, `model_b_ceiling.py` and `tier2_settle.py`.

**It now fails loudly rather than silently.** It used to return zero — indistinguishable from a
healthy idle engine, so `counts()` reported no node processes and `kill_orphans()` reported a clean
teardown while leaving every orphan running. `counts()`, `kill_orphans()` and `check_node_mark()`
now compare the **declared** pattern against the **measured** process table in the same snapshot,
and raise `NodeMarkStale` — naming the pattern, an example command line, and the override — when
the pattern matches nothing while processes ending in `engine/ai/node.py` are running. With an idle
engine both counts are zero and there is nothing to compare, so that case reports
`conclusive: False` rather than claiming a pass.

Guarded by regression test `node_mark_fails_loudly`, which drives a synthetic process table (no
engine needed) and covers four cases: renamed tree raises, `RR_NODE_MARK` override resolves,
default pattern on the original tree still matches, and an idle table does not raise.

Unrelated and **must not be changed**: `SEED_NAMESPACE = "benchmark-A/v1"` in
`working/harness/seeds.py` and `working/handoff/seeds.py`. It is a seed namespace, not a path.
Editing it changes every derived seed and invalidates reproduction against
`working/results/fault_matrix/seed_proof.json`.

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

**⚠️ The venv lives OUTSIDE the clone, one level up.** Every command in this repo calls
`../.venv/bin/python` — 32 places across the docs and scripts. That is not a typo: this clone was
one of several sibling working directories sharing a single venv. **A clone with no `../.venv` cannot
run anything, including the regression suite the README tells you to run first.** Create it in the
*parent* of the clone:

```bash
cd "$(git rev-parse --show-toplevel)/.."   # the directory CONTAINING the clone
python3.12 -m venv .venv                   # Python 3.12.13; other 3.12.x should be fine
./.venv/bin/python -m pip install -r "$OLDPWD/requirements.txt"
```

Then, from inside the clone, the documented commands work as written:

```bash
../.venv/bin/python working/scripts/regression_selftest.py
```

`requirements.txt` at the clone root pins the full set. **Verified by clean install** — a fresh
3.12.13 venv, `pip install -r requirements.txt` and nothing else: all 14 versions resolve
exactly, `pip check` reports no conflicts, every package imports, torch/numpy ABI interop
works, and the LlamaIndex arm warms in 5.3 s and returns a 384-d unit-norm vector. Every
version in it was **read from the venv that produced the results**, not chosen — see the header comment for what is deliberately excluded
and why. `ENVIRONMENT.md` is the same set in prose.

> If you would rather keep the venv inside the clone, `.venv/` is already gitignored — but then
> every `../.venv/bin/python` in the docs becomes `.venv/bin/python`. Pick one and be consistent;
> a half-migrated tree silently runs two different interpreters.

## 5. Corpora (`corpus/` and `data/`)

**`corpus/` — GovDocs1 PDFs, ~5.9 GB. This is the corpus behind every headline result**, including
the matched replication and the NUL-truncation prevalence figure. Public domain, from
digitalcorpora.org:

```bash
../.venv/bin/python working/scripts/fetch_govdocs.py      # downloads and unpacks into corpus/
../.venv/bin/python working/scripts/corpus_characterize.py  # size/page distribution, sanity
```

Expect a long download. The corpus contains genuinely malformed PDFs on purpose — that is what
makes the fault classes and the 0.30 % NUL prevalence measurable, so do not filter it.

**`data/` — `mt10k`.** Rebuildable, and verified 10,000/10,000 by sha256 against Leela's manifest:

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
