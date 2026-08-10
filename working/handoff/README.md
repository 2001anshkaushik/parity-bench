# Reusable instruments for WS-1

Four standalone modules extracted from benchmark-A. **Drop them into Leela's repo wherever you
like — none of them import each other except `fault_injection.py → seeds.py`, and none require
adopting benchmark-A's structure.** No repo restructuring implied or needed.

Dependencies: `psutil` (collector only). Everything else is stdlib.

| file | lines | needs | drop into |
| --- | ---: | --- | --- |
| `seeds.py` | ~25 | stdlib | anywhere importable |
| `fault_injection.py` | ~140 | `seeds.py` | next to seeds.py |
| `tree_collector.py` | ~650 | `psutil` | anywhere importable |
| `test_collector_overhead.py` | ~80 | `tree_collector.py` | your test dir |
| `verify_frameworks.py` | ~560 | stdlib + `uv` (optional) | scripts/ |

---

## 1. `seeds.py` — deterministic seeding

**Problem it solves:** `hash()` on strings and tuples is salted per interpreter (PEP 456). We
seeded fault plans with `hash((fault, rate))` and the same nominal config injected **44 faults in
one run and 66 in the next**. Comparisons *within* a run stayed valid because all frameworks
shared one plan, but nothing was reproducible across runs — and nothing could be pre-registered.

```python
from seeds import seed_for
rng = random.Random(seed_for("faultplan", "hang", 0.05, 1000))
```

Verified identical across separate interpreters **and** across differing `PYTHONHASHSEED` values.
Bump `SEED_NAMESPACE` only to deliberately re-randomise a whole study; record it in results.

## 2. `fault_injection.py` — poison-run accounting

Addresses exec review action item #5. The accounting is the whole point:

```python
from fault_injection import make_plan, score, Deadline, control_passed

plan = make_plan(n=1000, fault="hang", rate=0.05, tag="mt10k")
dl = Deadline(seconds=20.0)                 # ONE wall clock, from batch start
results = {}                                # item_id -> (ok, value_or_None)
# ... run your service, using dl.remaining() as each item's timeout ...
row = score(plan, results, dl.elapsed(), reference_fn=my_reference)
```

Returns `injected`, `collateral_failed / _missing / _wrong_output`, `isolation_ratio`,
`goodput_pct`, plus the seed and plan fingerprint for reproducibility.

**Two traps it encodes, both of which produced false verdicts for us:**

1. **One wall-clock deadline from batch start, identical for every service.** Our
   `ProcessPoolExecutor` path called `fut.result(timeout=…)` inside `as_completed()`, which only
   sees *already-completed* futures — the deadline never fired, it ran to 100 s against everyone
   else's 20 s, and scored a fictitious perfect 0.00. A separate asyncio path started its timer on
   semaphore acquisition rather than batch start. Once symmetric, a "7× difference" between two
   frameworks vanished entirely.
2. **Always run a zero-fault control.** `control_passed(result)` gates on it. Our Model A cells
   reported ratios of 32 and 49 that were pure artefact — setup cost inside the timed region meant
   clean items timed out with no fault involved. The control scored 0% goodput and caught it.

**`collateral_wrong_output` is the field people omit and the one that matters most.** A service
that stays up while silently corrupting survivors scores as perfectly isolating without it. Swap
`reference_fn` for mt10k's offline reference vectors.

## 3. `tree_collector.py` — out-of-process metrics

```python
from tree_collector import ProcessCollector
with ProcessCollector("samples.jsonl", {"svc": {"pids": [master_pid]}}) as c:
    ...run the load...
print(c.summary())     # peak RSS, threads, fds, CPU-seconds, leak slope, macOS compressor/swap
```

Role specs are declarative (`{"pids": [...]}` or `{"pattern": "regex"}`) so they survive the
process boundary; both forms expand to **full descendant trees**.

**Two reasons it is built the way it is:**

- **It runs in a separate process on purpose.** An in-thread version slowed the measured system
  **100×** on macOS (5,412 → 58 items/s) because psutil's per-root `children(recursive=True)`
  rescans the whole process table while holding the GIL. The bias is *directional* — it throttles
  in-process frameworks and leaves an external engine untouched, fabricating a win out of nothing.
- **It walks trees; it never greps cmdlines.** uvicorn spawns workers via `multiprocessing`, so
  their cmdline contains no "uvicorn". On our own LlamaIndex service a cmdline census reported
  **"1 process, 19.6 MB"** while the tree walk reported **"16 processes, 3,404 MB, 90 threads"** —
  a 173× memory undercount. If WS-1 compares memory across three services, this single detail
  decides whether the comparison means anything.

**Run `test_collector_overhead.py` before trusting it on a new host.** It asserts both that
overhead is under 15% *and* that the baseline noise is below that tolerance — a tolerance is
meaningless if the measurement is noisier than it. On the M4 Pro: −6.1% overhead, 6.9% noise, PASS.

## 4. `verify_frameworks.py` — framework dossiers

```bash
python verify_frameworks.py llamaindex langgraph --install
```

Per framework, from primary sources only: PyPI identity and publisher, licence and whether it
permits publishing results, release recency (flags STALE / ABANDONED), isolated install into a
disposable venv, import check, vendor-endpoint and telemetry detection, and Track A/B eligibility.
Anything it cannot establish is recorded `UNVERIFIED`, never inferred. Writes `.md` + `.json`.

**Two bugs fixed on 2026-08-05 while running LlamaIndex through it** — if you have an older copy,
take this one:

- **False `ModuleNotFoundError`.** It derived the import name from the distribution name by
  `dash → underscore`, giving `llama_index_core`; the real import is `llama_index.core`.
  Namespaced packages broke the naive rule. Now tries several spellings.
- **False "depends on another framework under test".** `llama-index-core` matched the token
  `llama-index` against *itself*. Now excludes self-tokens.

**Known limitation:** vendor-endpoint detection is a heuristic on source text and yields
`REVIEW_REQUIRED`, never a verdict. LlamaIndex trips it on `api.cloud.llamaindex.ai` (LlamaCloud,
their hosted product) even though the local path needs no account. Locality must be settled
behaviourally — construct the thing and run it with every API-key env var unset. That probe is
~30 lines and worth writing per framework.

---

## Suggested order of adoption

1. `seeds.py` — five minutes, unblocks reproducibility for everything else.
2. `tree_collector.py` + its test — before any memory or CPU number is taken seriously.
3. `fault_injection.py` — when poison runs start (action item #5).
4. `verify_frameworks.py` — once, per framework, before building on it.

Happy to walk through any of these or adapt them to your interfaces. They are deliberately
boring, dependency-light files rather than a framework — lift what is useful and discard the rest.
