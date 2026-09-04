# Methodology register — DRAFT (placement is Ansh's, per the 2026-08-20 ruling)

Entries 1–3 and 5: one lesson from four directions — in each, the thing
consulted was upstream of the thing that runs. Entry 4 is a different failure
mode with the same generalization. Entry 1 is reproduced VERBATIM from the
session record where it was drafted — recovered from the transcript rather
than rewritten from memory, which is entry 2's point in miniature.

## 1. A source trace is not a measurement (drafted 2026-08-20/21)

> **Methodology entry — a source trace is not a measurement.** The video-phase
> preflight predicted chunk_size=512 from a correct, cited read of the
> engine's config-resolution path, and the prediction was wrong: a
> constructor-kwargs filter downstream of everything traced discarded the
> configuration, and LangChain library defaults (4000/200) ran. The records
> adjudicated in one query; the trace had missed one function. Symmetrically,
> the reviewer flagged `chunk_config_parity((4000,200),(4000,200))` as
> config-asserted-as-evidence — and the operator's "measured pair" comment
> turns out to have been the measurement-backed side. Rule reaffirmed in both
> directions: a chain of source citations is still an assertion until a record
> agrees with it; and when flagging someone else's number as unmeasured, check
> first whether yours is.

## 2. Self-consistency is not evidence — the check must cross an independence boundary (added 2026-08-21)

> **Eight self-consistent sites are one observation, not eight.** Every
> video-tree file imported `RocketRide`, a class that exists in no generation
> of the SDK surface — eight sites across six files, written from one act of
> recall, none executed. Their perfect agreement measured the author's
> consistency, not the world: all copies descend from the same memory, so no
> check that samples the author's output against more of the author's output
> can catch the fabrication. **The check has to cross an independence
> boundary**, and there are only two: execution, or an artifact the writing
> did not produce (the incumbent measured corpus, the installed package).
>
> Entry 1 is the same lesson approached from the other side: there, a correct
> chain of citations substituted for a record; here, a consistent chain of
> copies substituted for a surface. In both, the thing consulted was upstream
> of the thing that runs.
>
> Shipped form: `working/video/sdk_identity.py` — the verified surface as an
> artifact (names AND parameters, each citing measured evidence), checked
> statically before first execution (`--scan`: laptop-side and bake stage 0)
> and live at every preflight (`readback()`), both null-controlled. Ordering
> rule for the next time many call sites get written before any run: mint the
> verified list FIRST, from a cited measured exemplar, then write the sites
> against it — the incident happened because the sites came first and nothing
> existed for them to disagree with. Decision recorded (2026-08-21): the
> two-step cost this imposes on legitimate surface extensions is accepted —
> the right trade against a fabricated API surviving eight copies.

## 3. A measurement is bound to the conditions it was taken under (instance seven, added 2026-08-21)

> The bake's readiness check — `socket.create_connection(('127.0.0.1',5565))`
> — was a real measurement once. Under Phase 1's `--network host` (carryover
> section C), a TCP accept could only come from the engine, and the predicate
> was measured meaningful there. The video tree started containers with
> `-p 5565:5565`, where docker-proxy binds the published port the instant
> `docker run` returns: the same line kept passing while measuring the
> FORWARDER's readiness, not the engine's ("stream ends after 0 bytes, before
> end of line" — the websocket handshake hit a forwarder with nothing behind
> it). **Nothing about it looked like an assumption — it had been a
> measurement.** The condition it depended on (network mode) traveled out
> from under it silently, and it became an assumption again without a single
> character changing.
>
> Beside entries 1 and 2: a citation chain is not a record; a chain of
> self-copies is not observations; and a past record is not a present one
> when its conditions have moved. Two rules shipped (2026-08-21): **measure
> the thing you need, not a proxy for it** (operator's phrasing — readiness
> for SDK traffic is a real SDK `connect()`, which no network topology can
> fake; `working/video/probe/wait_ready.py`, one helper everywhere a
> container starts), and a condition a measurement depends on becomes a
> RECORDED, checked value the moment the measurement is reused — Crossroad
> 22: `--network host` on both arms (docker-proxy is a userspace hop inside
> measured latency, and Phase 1 comparability allows no silent deviation),
> read back fail-closed at preflight and recorded in provenance, never
> implied by the flag that requested it.
>
> **Addendum, 2026-08-22 — a relative path is a shared assumption about cwd,
> and it crosses process boundaries silently.** `ProcessCollector` passed the
> caller's (relative) output path to a child it starts with
> `cwd=<repo>/working`. Phase 1's drivers ran FROM `working/`, so both sides
> resolved it identically and the code was correct for a whole phase. The video
> driver runs from the repo root: the child resolved the same string against
> `working/`, wrote `working/working/video/results/.../collector_*.ready`, and
> sampled happily — while the parent polled the original string and timed out.
> **The readiness timeout meant "your paths disagree", not "the child is
> dead"**, which makes both obvious fixes wrong: raising the timeout waits
> longer for a file that will never appear, and changing the caller's cwd makes
> the collector's correctness depend on who called it — which IS the bug. The
> fix is to resolve to absolute in `__init__`, before either side can use the
> value. Two rules: **a path handed across a process boundary is absolute or it
> is a bug waiting for the cwds to differ**; and **an error message must name
> what it was watching** — "did not become ready within 30s" was diagnosable
> only by finding the stray file on disk, so it now prints the resolved path
> and the child's cwd. Audited the same day: in the video path this was the
> only relative path crossing a boundary (every `docker exec` path is absolute
> in-container, every `use(filepath=)` is ROOT-derived; the only other `cwd=`
> override is a Phase 1 handoff copy of this same class, flagged not changed).

## 4. An unexecuted string (added 2026-08-21)

> Not an identity claim — just a string: a Dockerfile ENTRYPOINT is a shell
> command inside a JSON array inside a Dockerfile, three quoting layers deep,
> and none of them executes before the first build. `bash -n` cannot see
> inside a JSON array; **first build is first execution**. The generalization
> is entry 2's — nothing that has never run is verified — and the shipped
> check is smoke section 0b: shlex-parse every ENTRYPOINT/CMD sh string,
> every flag and constrained value against an allowlist measured from
> uvicorn's own CLI source, mid-word `--` flagged as a missing space,
> null-controlled.
>
> Companion (2026-08-21): **a command that warns and exits zero is a failure
> wearing a success's clothes.** `aws s3 cp <(git show …)` printed "Skipping
> file /dev/fd/63" and returned 0, so the `&&` chain sailed on and the upload
> looked done; the same day, a `head`-truncated bucket listing nearly read as
> "no files here". Both caught the same way: by re-measuring the outcome
> (does the object exist? what does the FULL listing say?), never by reading
> the exit code.

## 5. Arithmetic from a measured input is still an assertion (Crossroad 23, added 2026-08-21)

> floor(duration/15)+1 said 84; the arms' ffmpeg emitted 83 — the t=1245 slot
> never fires on a 1248.3 s stream. **The duration was measured; the frame
> count was not** — the formula encoded our model of `fps=1/interval`, not
> ffmpeg's. And no corrected formula replaces it: a replacement
> reverse-engineered from one observation on one file would fit the check to
> the result, which is what the gate exists to prevent. The expectation
> column is now MEASURED at manifest build, through the same binary the arms
> use, fed by the same pipe the arms use; formulas survive only as labeled
> planning estimates. Kin to entry 1: a derivation is a trace through
> idealized semantics — and the semantics are an environment too.

## 6. A provenance change follows the value to every consumer (added 2026-08-21)

> The manifest already carried an expected-frames column when Crossroad 23
> made expectations measured — and the driver never read it. It recomputed
> the same formula from the duration, privately; the old fetch docstring even
> NAMED the twin ("same formula as driver_video.expected_frames") — the two
> copies were kept consistent by comment, not by reference. Fixing the
> producer alone would have changed nothing: the wrong arithmetic would have
> kept running inside the consumer, wearing the manifest's new authority.
> **When a value's provenance changes — derived → measured, assumed → read
> back — every consumer is audited for a private copy of the old
> derivation; the grep is part of the change, not a follow-up.** Kin to
> entry 2: the second copy was perfectly self-consistent with the first, and
> nothing ever looked.
>
> **Addendum (reviewer's, 2026-08-22) — the second copy is not always in
> another file.** The quiet-box gate's return shape changed and both callers
> kept formatting the old keys — in their *PASS branch* each — so the happy
> path died on a KeyError while the failure path stayed correct, inside the very
> commit that was fixing an attribution bug. **Sometimes the stale copy is the
> other BRANCH of the same feature**: it does not run when the change is
> tested, so the change cannot break it visibly, and it waits for the first run
> that takes the other path — here, leg four of an 80-minute campaign at 2 a.m.
> The cure is the usual one applied a level up: not "fix both copies" but *have
> one copy* — a single `quiet_box_line()` shared by driver and smoke across
> both verdicts, plus a self-test that calls producer and formatter together so
> a key change breaks a test rather than a run.

## 7. A disqualified command that stays quotable will get quoted (added 2026-08-21)

> The Crossroad 24 recheck ruling disqualified `PROBE_MATRIX=32 probe_run.sh`
> by name — it drags four other stages along and overwrites the original
> evidence — and supplied a safe extracted sequence instead. Hours later the
> disqualified form was relayed and run, and the original t32 JSON was
> clobbered by the very run meant to confirm it. The disqualification lived
> in one report; the familiar, quotable command lived in another — **the
> correction and the thing corrected were in different places, kept aligned
> by nobody** (entry 6's shape, at the level of operations instead of code).
> The durable cure is not a louder warning but making the dangerous form
> safe: probe_run now moves any existing output aside as `*.prev_<ts>`
> before writing (a name no `*.json` glob reads), so the quotable command
> can no longer destroy evidence when — not if — it gets quoted.

## 8. A guard that checks presence rather than plausibility cannot fail for the case it was built for (added 2026-08-21)

> The probe-derived build arguments refused to DEFAULT — and bounded nothing
> about what a present flag could carry. The trigger was a relayed
> missing-space line (`25.95--measured-chars-per-det … rc=0, manifest
> written`); reproduced against the committed code, argparse's `type=float`
> in fact REJECTS that exact string — but the reproduction surfaced what the
> parser quietly accepts instead: **prefix abbreviation** (`--measured-chars`
> silently matched `--measured-chars-per-det`), which fits the observed
> rc=0-with-60-rows — with CORRECT values — better than the relayed line;
> the manifest meta adjudicates. Either way the class is real: nothing
> validated ranges (2595.0 would have sailed through where 25.95 was meant),
> and an abbreviated flag is an unmeasured identity claim. Fixed as a class:
> every numeric argument in the video tree parses through validated types
> (range + '--'-in-value rejected naming the missing-space hypothesis;
> null-controlled self-test in argtypes.py), every parser sets
> `allow_abbrev=False`, and run_plan's eight env vars are number-validated
> after their presence checks. Kin to entry 4's companion — failures wearing
> a success's clothes, at the argument parser instead of the shell. The
> reproduction itself donated a specimen: the checker printed `$?` after a
> pipe and displayed tail's success for every case — `${PIPESTATUS[0]}`, the
> campaign's oldest defect, caught live in the checker's own frame.

## 9. The reading is not the artifact (the reviewer's own entry, drafted in their name as ruled, added 2026-08-21)

> Three wrong diagnoses in two days, mine, all by the same mechanism: I read
> a terminal rendering and reported it as the artifact. The Dockerfile
> ENTRYPOINT "missing space" — the repo file had the space; byte-level greps
> and a green build adjudicated. The RR thread curve "produced nothing" — my
> query used key names that do not exist in the probe's schema; the same
> files were simultaneously passing gate-3 staging. The argparse guard
> "defeated by a missing space with rc=0" — the relayed line reproduces as
> REJECTED by the committed parser; the plausible culprit was a different
> line the parser quietly auto-completed. Each time the reading felt
> sufficient; each time the agent reproduced against the code or the box and
> the reading lost. **The operating rule: when the advisor has a hypothesis
> about what a command DID, the adjudicator is the code or the box — never
> the reading.** Scrollback is a rendering: it truncates, stitches, wraps,
> and duplicates, and it does so without marking where. The same day, the
> agent's own reproduction harness printed `$?` after a pipe and displayed
> success for every failing case — the campaign's oldest defect, live inside
> the checker built to adjudicate my error. That is the best argument this
> register has that these rules must be structural — in parsers, in
> preserve(), in read-backs — rather than remembered by anyone, reviewer or
> agent.

## 10. A broken tool masked a broken predicate (added 2026-08-21)

> The LI worker census returned zero because its `docker exec ps` found no
> ps — python:3.12-slim ships no procps. Behind that loud zero sat a second,
> quieter defect: the census filtered argv for `uvicorn`, and the measured
> tree shows that string appears in exactly ONE process — the non-serving
> master; the workers are multiprocessing `spawn_main` children. **Fixing
> only the tool would have produced serving=1 at every W: a plausible wrong
> number, worse than the obvious zero.** Layered failures order themselves
> by loudness, and the first one found is not the last one there. The cure
> that survives is not sequential debugging but an independent ground truth
> inside the loop: every response carries its serving pid, and the census
> must contain it or the run reports CENSUS BLIND with the full process
> tree attached — the failing run carries its own fix. Kin to entry 4's
> family, with the inversion made explicit: an obvious zero invites exactly
> the fix that installs the plausible wrong number.
>
> **Addendum, same day — the lesson recurred inside its own fix.** The
> replacement predicate was pinned against the measured W=2 tree
> ('spawn_main' children of pid 1) and the very next run, at W=1, the blind
> branch fired again: the response pid was 1 — the master (hypothesis,
> pending the W=1 tree dump: uvicorn with --workers 1 serves in-process
> without spawning). One configuration's measurement is not a predicate for
> all configurations. The pattern approach was retired outright (reviewer's
> ruling, agent concurring): serving is now DEFINED by measured behavior —
> the processes that burned CPU during the batch — anchored by ground truth:
> every response pid must appear among the burners, a deliberately
> non-trivial membership check (against the burner set, never the
> everything set) so the instrument still self-verifies. argv strings remain
> as attribution text on each process, never as a predicate. The RR census
> keeps its pattern, stated as the honest asymmetry: it was
> execution-verified in its actual configuration, and RR responses carry no
> pid, so no ground-truth anchor exists there to invert onto.

## 11. Check the benign explanation against the points already in hand (added 2026-08-21)

> Six of eight workers serving looked like accept-routing luck — and the iid
> arithmetic even agreed: 8 posts into 8 workers expects ~5.25 occupied. But
> the SAME mechanism predicts ~2.7 of 4, and W=4 had served 4-of-4 in the
> same sweep. The benign explanation was inconsistent with data already
> collected — falsified before a single new run was spent on it. The method,
> stated as one: **when an anomaly has a plausible benign explanation, first
> check that explanation's predictions against every point you already
> hold — the cheapest experiment is the one already run.** The discriminator
> still runs: falsifying "benign routing" does not by itself prove "dead
> workers"; it narrows the hypothesis space and re-prices the follow-up.
> Kin to entry 1: a plausible mechanism is an assertion until a record
> agrees with it — including the records already sitting in the output
> directory.

## 12. The asymmetry we audited in Phase 1 was reproducing in Phase 2 while we wrote the argument against it (added 2026-08-22)

> The reviewer ordered a tuning-symmetry audit, our own arm first and
> harshest. Phase 1's finding was bad enough: `FAIRNESS_BASIS.md` claims
> best-to-best and discloses LlamaIndex's workers "tuned to a measured knee"
> of 8, but that knee was measured on the laptop; the box ran 32, adopted from
> a teammate's convention in answer to an exec's fairness objection, and
> **neither arm was ever swept on the box**. We wrote that up as a correction
> owed to Monday's report.
>
> Then the same audit turned on Phase 2 and found the defect still running.
> The RocketRide arm had seven refine points and a full M×T budget line
> (Crossroads 29–31); the LlamaIndex arm had two points at one worker count
> and no budget line at all — the exact shape of the error Crossroad 30 had
> just caught on the RR side. Forced onto the same method, the LI budget line
> moved `LI_THREADS_ENV` from 1 to 4: **0.0871 → 0.1340 videos/s at the same
> worker count, 54% of the arm's own measured throughput left on the table**,
> and a real knee (W=8/T=4 turns over, unlike RR's). We were days from
> publishing an argument about method symmetry while running the competitor
> arm 54% below its measured optimum.
>
> Two rules. **A correction in one phase does not carry to the next**: the
> asymmetry is not a mistake anyone made, it is the gradient the work sits
> on — every one of the three benchmarking teams works for one of the two
> vendors, so effort flows to the home arm by construction and reappears
> wherever it is not actively opposed. **So the audit is scheduled, not
> triggered by suspicion** — a suspicion-triggered audit only fires where
> someone already doubts, which is never the arm nobody is defending. Kin to
> entry 1 in the sharpest way available: "we run best-to-best" was an
> assertion *about our own method*, and it survived two phases without a
> record agreeing with it.
>
> Shipped with the finding, because the number itself was still unverified:
> `probe_li_workers` set six thread variables on the container and recorded
> nothing about what the workers got. `wait_ready.li_worker_thread_readback()`
> now polls `/health` until EVERY worker pid has answered, reports each one's
> in-process `torch.get_num_threads()`, and the sweep REFUSES a point whose
> declared thread env cannot be read back from every worker
> (INCOMPLETE/DISAGREE/MISMATCH/OK, all four exercised). A sweep that cannot
> prove its own configuration landed is measuring an unknown configuration —
> and it was about to set a run-plan number.
>
> **Addendum (reviewer's, 2026-08-22) — the class, counted.** Config asserted
> as evidence has now been found in five places: in the harness
> (`chunk_config_parity` reporting a configured pair as measured, entry 1); in
> the engine (Ticket 3 — a chunk config that is accepted and silently
> discarded); in the census (declared workers taken for serving workers, entry
> 10); in `env_probe` (a field absent from a stale node, read as a value,
> 2026-08-22); and now in `probe_li_workers` and `probe_concurrency` — code we
> wrote THIS WEEK, while auditing two teammates for exactly this. **The rule
> that follows is not "be careful."** It is: *any value that sets a run
> parameter must have a read-back before it is quotable, and the read-back is
> part of the probe, not a follow-up.* A probe that emits a number it cannot
> also prove the conditions of has not finished; the read-back is not
> instrumentation around the measurement, it is half of the measurement.
> Shipped on both sides the same day: `wait_ready.li_worker_thread_readback()`
> (every LI worker's in-process torch count) and
> `probe_rr.verify_task_thread_env()` (every RR task process's own
> `/proc/<pid>/environ`), each refusing the point rather than recording it at
> an unknown configuration, each null-controlled. Honest boundary, stated in
> both: `/proc/environ` proves the variables reached the process, not that
> torch read them — only an in-process `torch.get_num_threads()` (the
> env_probe node, run by the driver's preflight every leg) closes that.

## 13. The instrument reported our own history as somebody else's present (DRAFTED 2026-08-22 — placement is Ansh's)

> The quiet-box gate asked "is foreign work running on this box?" and answered
> it with `load1`, a ~60-second exponentially-damped average. That was a real
> measurement in Phase 1, where nothing of ours ran between legs. Phase 2 chains
> nine legs back to back, and a blast leg runs the box at ~23 of 32 cores: when
> it ends, load1 needs **~150 s** to decay under the 2.0 threshold
> (23·e^(−t/60)), while the next leg's preflight reads it ~15 s later. **Legs
> 2–9 would each have failed a gate whose entire purpose is catching somebody
> else's hog** — aborting the campaign at leg two, in the name of a hog that was
> our own previous leg.
>
> Two things made it invisible. First, entry 3's mechanism: nothing about the
> gate changed, the conditions moved out from under it — our own workload grew
> until it dominated the instrument's memory. Second, **no dry pass could ever
> catch it**: a dry pass clamps every leg to n=1, and an n=1 leg leaves no tail.
>
> **THE FAILURE REQUIRED EXACTLY WHAT THE REHEARSAL REMOVES** (reviewer's, and
> the part that generalises furthest). This is a rule about rehearsals, not
> about load averages. **A clamped rehearsal validates WIRING and is
> structurally blind to anything that emerges from SCALE or SEQUENCE** — load
> carried between legs, contention and queueing at real concurrency, memory
> growth, drain tails, anything a second pass exercises. The very clamping that
> makes a rehearsal cheap deletes the conditions the interesting failures need.
> So a green dry pass is never evidence that the run will hold; it is evidence
> that the wiring holds, and the two must be said differently. Written into
> `run_plan.sh`'s header as an explicit can/cannot list, because the person
> reading a green dry pass at 2 a.m. is the person most likely to over-read it.
>
> The rule: **an instrument that averages over time cannot gate an interval
> shorter than its own time constant** — and when the thing you are excluding
> is your own recent work, a lagging instrument will always find it. Gate on the
> instantaneous quantity (host busy cores from /proc/stat, minus our containers'
> cgroup rate, minus our own process tree, all over one window); keep the
> lagging one recorded beside it, because load1 is what caught the 18-Aug hog
> and what Phase 1 published. Related: entry 3 (a measurement is bound to its
> conditions) and the same day's finding that the gate subtracted only
> containers, so every process of OURS on the host — driver, smoke, `docker`
> calls, the console tee, and run_plan's own full-corpus sha256 — was charged
> to a hog.

## 14. The assert went in where the bug was seen, and the twin ten lines up kept running (added 2026-08-23)

> `sorted(glob('probe_li_floor_t*.json'))[-1]` is lexicographic: with
> t1/t2/t8/t32 on disk it returns **t8**. Five sites selected a cross-arm
> artifact that way, and each was patched *at the site where the failure had
> been observed* — so the identical defect resurfaced one site later, on the
> next corpus, three times running: the early identity step (patched
> `4c659541`), gate-3 staging (patched `78d630f0`), then gate 4, the
> frame-count agreement check, and the thread-curve summarizer, all still
> live. Every patch was correct. Every patch was also the whole response.
>
> **The sharpest part is what the third patch actually did.** Its diagnosis
> read "the post-matrix compare the deferred branch promises does not exist",
> and it *added one* — beside the existing post-matrix compare, which had been
> there since `01b82de`, which was broken, and which is the one that then
> reported `n_engine=93 n_li=83 — decode paths differ` from a two-day-old
> Corner floor. Two comparators for one gate; the asserted one passed and the
> unasserted one printed the verdict. **A broken implementation was mistaken
> for a missing one, and the replacement was built instead of the original
> being found.** The mechanism is banal and worth naming: the search was for
> the *identity check* — the shape of the fix — and code that has never had
> the check does not contain it. **Grep for the OPERATION, never for the
> defect's signature and never for your own fix**; enumerate every site that
> compares, then fix them together or, better, make them one.
>
> Shipped as one copy, per entry 6's addendum: `probe/artifact_identity.py`
> holds the only selector (`select_by_video`, `select_all_by_video`,
> `require_same_video`) and every site calls it — the duplicate gate-4
> comparator is deleted rather than fixed. Note also the fix that was NOT
> made: "take the newest instead" is an **ordering** fix for an **identity**
> bug — right today, wrong the first time a probe re-runs out of order or a
> floor is copied in. Identity is not a sort key.
>
> **Second half, the reviewer's, and it generalises past globs: a comparator
> that cannot prove same-input has not found a difference.** The standing
> policy — on a cross-arm mismatch the REAL-DIFFERENCE hypothesis comes first,
> never tolerance — is correct, and it silently assumes both sides read the
> same input. When that is unproven the honest verdict is not "real
> difference" but **CANNOT COMPARE**: a fault in the EVIDENCE, not a finding
> about the ARMS. Until now both printed the same sentence, so a true positive
> and a stale-file bug were indistinguishable in the log — and the log is what
> gets relayed. Now three verdicts with three exit codes (0 PASS / 1 REAL
> DIFFERENCE / 2 CANNOT COMPARE), and `real_difference()` **raises** unless
> handed the `video_sha16` proven on both sides. The entitlement is
> structural: the only way to print the sentence is to hold the proof that
> earns it.
>
> Two smaller things the day donated. The summarizer was not merely a
> reporting tool — it emits `--measured-dpf` and `--measured-chars-per-det`,
> the Crossroad-23 manifest re-cut inputs, so pooling across corpora would
> have re-cut the manifest from blended numbers; it now groups by recorded
> identity and refuses more than one video unless `--all-videos` makes the
> pooling explicit (entry 12's addendum: a value that sets a run parameter
> needs a read-back before it is quotable). And the harness written to catch
> stale copies was itself testing a stale copy — it extracted the shell blocks
> once and kept comparing against that snapshot across edits, passing a check
> it should have failed. It now extracts from the live file every run. Kin to
> entry 9's ending, and the same argument: these rules only hold when they are
> structural, never when they are remembered.

## 15. A default that was right for one corpus, and a tool that fetches when it should refuse (added 2026-08-23)

> The campaign died at step 0, four minutes in, nothing measured. `run_plan`
> called `fetch_ami_video.py --verify` with no `--corpus-dir`; the tool's
> default was `corpus/ami/video` — correct for the Corner corpus, and silently
> wrong for ami_full at `corpus/ami/full`. It found every file "missing", and
> its answer to "missing" was to reach for the network: `urlopen('')` on a
> staged row, because the fetch loop ran before the verify loop whatever flag
> was given. Ansh's by-hand verify had passed because he passed the flag.
>
> **Two faults in one line, and both are classes.** (1) *A default that names a
> corpus is a measurement bound to the corpus it was written against* (entry 3's
> shape, at the level of paths): it stays correct until the corpus moves, then
> becomes wrong without a character changing — and this is the THIRD instance in
> two days. The PDF fixture corpus (2026-08-22, `run_plan` now passes
> `PDF_CORPUS` explicitly for exactly this), the golden path the same night, and
> now the video corpus. (2) *A verify must never fetch.* "Check what is on disk
> against the manifest and report" and "go and get what is missing" are two
> operations; one was wearing the other's flag, so a wrong path turned a read-only
> check into a download attempt. Kin to entry 4's companion: the tool's response
> to a negative finding was to manufacture a positive one.
>
> **And the sweep found it was not one omission but three.** `fetch_ami_video`,
> `smoke_video` and `driver_video` each carried a private copy of the same
> default, and `run_plan` passed `--corpus-dir` to none of them — step 0 was
> simply the first to die. The smoke's own corpus read-back even invoked the
> fetch mode (no `--verify`), so with the wrong directory it too would have
> downloaded. Entry 14's shape exactly: fix the site you saw fail and the twin
> keeps running. Three steps would have died in sequence, each asking for one
> more flag, each fix correct and each fix the whole response.
>
> Shipped as a rule with one copy, not three patches. **No tool carries a default
> that names a corpus.** The manifest records the directory it was built or
> stamped against (`_meta.corpus_dir`, earned by a full sha256 verify —
> `--stamp-corpus-dir`, meta line only, data rows asserted byte-identical);
> every consumer derives from it through `corpus_locator.py`; an explicit
> `--corpus-dir` must AGREE with it or the run refuses, naming both paths; a
> manifest that records none refuses and names the stamp command. `run_plan`
> resolves once through the same locator and passes the value — and its
> SOURCE, logged beside it — to step 0, the smoke and the driver. The four
> manifest operations are now named and exclusive: verify-size (default, the
> smoke's fast check), `--verify` (sha256), `--fetch-missing` (the only one that
> touches the network, and it refuses a staged row by name), `--stamp-corpus-dir`.
> `fetch_url('')` raises before the socket. Controls: 33, with a tripwire on the
> network so a verify that reaches for a download fails the test rather than a
> campaign.
>
> The general form, for the next corpus: **when a value is right because of
> where it was written, it is not a default, it is a recorded condition** — and a
> recorded condition lives in the artifact it describes, not in each tool that
> happens to need it. The manifest already described the corpus; it just did not
> say where the corpus was.

## 16. Four anomalies, one behaviour: a kernel accept queue is not a scheduler (Crossroad 40, added 2026-08-23)

> The campaign died at leg 2's warm-up: 18 sends could not reach two of eight
> LlamaIndex workers. It was the FOURTH instance of one behaviour we had been
> treating as four separate events: W=8 census 6/8 at 8 concurrent posts (iid
> predicts ~5.25 — resolved as routing luck), W=16 sweep serving 15/16 with the
> CPU collapse, a smoke /health read-back at 7/8, and now warm-up 6/8 at 18
> sends. Named: **uvicorn workers are selected by the kernel at accept, and
> low-concurrency traffic does not distribute** — a lone post goes to a
> recently-active worker (LIFO wake-up), so sequential sends can hammer one
> hot worker indefinitely, while concurrent posts wake the herd and spread.
> The measured curve, all points already in hand: 1x-workers concurrency
> reached 6/8; 2x reached 4/4 (the W=4 point); 4x reached 8/8 reliably (the
> Corner discriminator).
>
> The warm-up had the defect in its structure: a concurrent FIRST BATCH of
> `min(WARM_N, 2 x conc)` followed by a strictly SEQUENTIAL top-up loop. On
> Corner (WARM_N=16) the first batch was 16 concurrent sends and always
> covered — the sequential top-up never had to work, so its inability to
> distribute stayed invisible. ami_full set WARM_N=2 (Crossroad 32, her
> corpus's warm-set size), the first batch shrank to TWO sends, and coverage
> fell to the coin-flip machine: leg 1's warm-up passed by luck, leg 2's
> failed. **A parameter change two crossroads earlier turned a latent
> structural defect into a campaign abort** — entry 3's mechanism (the
> condition moved out from under a working thing) wearing entry 13's clothes
> (nothing about the code changed).
>
> **Crossroad 40 — fix the distribution, not the threshold.** Warm-up sends go
> CONCURRENT, in waves of `max(2 x declared workers, the leg's own
> concurrency)`, two waves maximum (cumulative 4x workers — the discriminator's
> proven load), re-sending the warm SET per Crossroad 32. The coverage rule is
> UNCHANGED: an unwarmed worker serving its first inference inside the measured
> window inflates the LlamaIndex arm's latency — our own comparison arm — so
> relaxing it would be a shortcut that damages the comparison in our favour's
> mirror. The RR arm is structurally immune and its Corner-banked arithmetic is
> untouched: tokens are DRIVER-ADDRESSED round-robin — coverage by
> construction; kernel accept plays no part. Confirmed from code, not assumed.
>
> **The instrument gap mattered as much as the bug.** The failing gate printed
> a COUNT — 6/8 — and discarded which pids served and how many sends each drew,
> so "distribution or dead workers?" could not be answered from the record
> (entry 10's rule broken: the failing run must carry its own diagnosis).
> Warm-up now writes a per-send ledger (row, pid, token, wall, error) plus the
> declared pid set BEFORE any verdict, and the gate names the unserved pids and
> the per-pid counts. The two hypotheses now separate in the artifact: pids
> missing after two waves at 4x concurrency = workers that never draw work
> (a different bug — the message says so and forbids raising the budget);
> scattered shortfall at low concurrency = distribution. One caveat is recorded
> in the ledger itself: pid identity is comparable only within one container
> lifetime (defect #23), so cross-artifact pid matching must check lifetimes
> first.

## 17. The probe and the gate were not measuring the same thing (added 2026-08-23, pending Ansh's ruling)

> Crossroad 40 made warm-up sends concurrent and the next run still failed:
> 32 sends in two waves of 16, three pids unserved, one worker taking ten.
> The reviewer's own failure text was the discriminator — same pids missing at
> 4x-worker concurrency is not distribution — and the natural next question was
> why `probe_li_workers` reaches 8/8 where the driver does not. Two hypotheses
> were on the table: connection pooling (a reused keep-alive connection stays
> pinned to one worker), and container age. Both were checkable without another
> eight-minute run, and neither survived contact with the code.
>
> **The post paths are identical.** Both build a fresh
> `urllib.request.Request` per post and call `urlopen`, both driven by
> `asyncio.to_thread` inside `asyncio.gather`. Measured rather than read: a
> keep-alive-capable local server, driven by the driver's exact shape, accepted
> **14 distinct TCP connections for 14 requests** with `Connection: close` on
> every one. No pooling exists to pin anything. (The first run of that
> instrument reported 9 connections for 14 requests — `id(self.connection)` is
> recycled by CPython after GC. The instrument was wrong, not the finding;
> re-measured by client source port. Entry 9, again, inside the check built to
> settle a hypothesis.)
>
> **What actually differs is what each one COUNTS.** `probe_li_workers` records
> two censuses: `serving_by_cpu_delta` — processes that burned CPU during the
> batch, which its docstring calls the serving proof — and
> `distinct_response_pids`, reported alongside, with the explicit note that
> **`distinct_pids < W` on one batch is scheduling, not a defect**. The
> driver's warm-up gate counts only distinct response pids. So the probe's
> headline 8/8 and the driver's fatal 5/8 may be two different measurements,
> and the gate may be demanding a result the probe never demonstrated and
> documented as not to be expected. `probe/which_8_of_8.sh` settles it from the
> probe's own artifacts in one command.
>
> **And the mechanism says client concurrency cannot force the result the gate
> wants.** `/process_video` is `async def` and offloads the model call with
> `anyio.to_thread.run_sync`, so a worker's event loop is never blocked: one
> worker can accept an unbounded number of concurrent connections and queue
> them, returning to `accept()` immediately. Concurrency raises the ODDS of
> distribution; it cannot compel it. Crossroad 40's premise — "concurrent posts
> force uvicorn to distribute" — is therefore true only statistically, which is
> the right fix for the wrong reason and explains why more load helped and did
> not settle it.
>
> The rule, and it is entry 1's with the roles reversed: **when two instruments
> disagree about the same system, check that they are measuring the same
> quantity before believing either.** Four "instances" of a worker-coverage
> anomaly were compared against a probe result that may never have been the
> same number. Related: the service already proves the property the warm-up
> exists to establish — every worker loads its model at startup and writes a
> warm marker, and `wait_ready --workers W` blocks until all W are warm — so
> "has this worker served a request" is a PROXY for "is this worker warm", and
> entry 3's rule about proxies applies: measure the thing you need. Recorded,
> not acted on: changing the gate's instrument is Ansh's ruling, and it is the
> difference between a shortcut and a correction.

## 18. Gating on a proxy we neither control nor need (Crossroad 41, added 2026-08-23)

> Three attempts failed the LI warm-up gate with DIFFERENT pids unserved each
> time — 6/8 [6,7]; 5/8 [10,11,13]; 6/8 [8,10] — which by the failure message's
> own discriminator rules out workers that never draw work and leaves
> scheduling. Severe scheduling: one worker took 12 of 32 sends, another took 1.
> Entry 17 had already found the mechanism: `/process_video` is `async def` and
> offloads the model call to a threadpool, so a worker's event loop never
> blocks and one worker can accept unbounded concurrent connections. **The gate
> was unachievable by construction** — Crossroad 40's concurrency raised the
> odds and nothing a client does can compel the kernel to spread accepts.
>
> The gate counted distinct response pids. The property it existed to enforce
> was "no worker serves its first inference inside the measured window". Those
> are not the same thing, and the service already proved the real one directly:
> every worker loads its model in `lifespan`, writes a warm marker, `/health`
> reports the count, and `wait_ready --workers W` blocks on it **before the
> driver posts anything**. Response-pid counting measured **uvicorn's
> scheduling** — a property we neither control nor need — and three runs were
> spent on it.
>
> **The distinction that made this a correction and not a shortcut, in the
> reviewer's words:** lowering the threshold to 75% would have accepted cold
> workers serving measured traffic — that is a relaxation, and it damages our
> own comparison arm. Asserting the same property through its direct instrument
> is not. The test is not "did the bar move" but "is the thing asserted still
> the thing that matters" — and here the direct instrument is strictly
> stronger, because a marker proves the model is loaded whereas a response
> merely suggests it. Warm-up still SENDS (first-inference and allocator state
> matter beyond marker presence) and still records the per-send ledger; only
> the verdict moved.
>
> **What was demoted is not discarded.** The response-pid spread is now
> exported — per-pid counts, busiest, quietest, unserved — and labelled
> REPORTED, NOT GATED. "One worker took 12 of 32 sends" is a real, measured
> observation about the LlamaIndex arm's behaviour under concurrent load, on
> our own comparison arm, and it belongs in the report rather than in a gate.
> A failed gate throws away the observation; a report keeps it. Kin to entry
> 10's cure — the instrument stays, its authority changes.
>
> Postscript, and it is the same lesson at one remove: `which_8_of_8.sh`, the
> tool written to settle which census the probe's 8/8 was, printed nine
> filenames and no rows. It filtered points on a key named `workers`; the probe
> writes `W`. **A guessed field name is a guessed path** (entry 15) and a
> guessed selector (entry 14) — the third face of one habit: selecting by a
> name you expect instead of by the property you need. It now walks the
> document for any object carrying BOTH census fields, whatever it is called or
> however it is nested, and says so plainly when a file carries neither.

## 19. The reaper was an idle timer, and every finite ttl is a movable cliff (Crossroad 43, added 2026-08-24)

> Leg 6 died in seconds: 16 concurrent sends, 16 errors, breaker, abort. Not
> resources (2/61 GB, 871 GB free, no OOM), no traceback — the engine log's
> only voice was CPython's child watcher substituting returncode 255 because
> the exit status was "already read". The stdlib reading held: 255 was the
> engine reaping its own child during a CLEAN termination — the thing being
> cleaned up was the cause. `task_server.py:331,365` (read on the box):
> **the ttl is an IDLE timer** — `if _idle_time >= _ttl: terminate` — and the
> diagnostic's timestamps closed it: container 02:58, failure 05:23, age
> 2h25m > ttl 7200. Zero 255-lines in the passing legs' logs.
>
> The driver passed `ttl=7200` believing it a generous lifetime; it was a
> deadline for a token to be USED. And the fix is not a bigger number:
> **any finite ttl is a cliff that moves** — the default-posture blast
> serializes 168 videos behind one device lock for ~2.7 h, so 7200 would have
> been crossed mid-leg even without idle gaps. Crossroad 43: `ttl=0` on
> measured legs (engine-documented: run until explicitly stopped), paired with
> the obligation that ruling creates — with ttl=0 there is NO reaper standing
> behind a failed terminate, so stop() now retries with a longer deadline and
> then says exactly what leaked and what it poisons (~1 idle core inside the
> cgroup the next leg's collector reads), instead of the old shrug "(recorded;
> ttl reaps)" — a sentence that had quietly become false the moment the ttl
> changed. The instrument tokens (envprobe 600, smoke golden 3600) KEEP their
> finite ttls deliberately: short-lived, terminated in finally, and a reaper
> behind those is protection, not a cliff.
>
> Two rules. **A timeout's unit of meaning is the thing it counts** — lifetime
> and idleness both arrive as "seconds" and nothing in the signature
> distinguishes them; the driver's belief was checkable in one grep of the
> pinned engine source, and it went unread until 00:00 with a campaign down.
> Kin to entry 3 (a measurement bound to its conditions) with the condition
> being a SEMANTIC, not an environment. And **when a safety net is removed,
> every message that mentioned it is now wrong**: the terminate-failure path's
> "ttl reaps" was true for two days and became a false reassurance with one
> changed argument. The grep for consumers of a changed value (entry 6)
> includes the SENTENCES about it.

## 20. The tidy mechanism explained the log line, and the timeline in hand already contradicted it (added 2026-08-24)

> The ttl closure was accepted at 07:00 — engine source read, idle timer
> confirmed, container age 2h25m > 7200 s, case closed — and it was wrong, or
> at least was not the cause of the blast failures: with ttl=0 landed and the
> engine confirmed skipping enforcement, the same leg died the same way six
> minutes after a fresh launch. The fact that falsified it had been in hand
> the whole time, in both failures: **warm-up had served on that token seconds
> before the first blast send**. A token that served seconds ago has an idle
> time of seconds. The ttl story required 2h of idleness that the leg's own
> log said never happened — entry 11's rule, run in reverse on ourselves: the
> benign-looking closure was never checked against the points already
> collected. The container-age arithmetic was a COINCIDENCE that fit, and a
> mechanism that explains the log line is not thereby the mechanism that
> killed the run. (ttl=0 stays: the idle reaper was a real latent cliff for
> the 2.7 h serial legs regardless.)
>
> Why three failures produced zero causal information: **the SDK discards the
> exception.** `dap_client.py:229` — `except Exception:
> raise ConnectionError('Could not send request')` — no chaining, no repr, no
> type. A websockets concurrency violation, a ping-starvation disconnect, a
> server rejection and a broken pipe all print the SAME SENTENCE. An error
> message that discards its cause manufactures the next wrong theory; ours
> cost two campaign nights. The probe now taps `DAPClient._send` and
> `TransportWebSocket.send` at class level and records the true exception
> before the wrapper eats it (`probe_m1_concurrency.py`).
>
> What the code settles while the probe waits: ONE websocket per CLIENT
> (tokens multiplex over it by seq — so parity's 16 tokens share one
> connection too); no lock anywhere in the send path; `send()` is not one
> request but pipe/open/write/close — a stateful sequence per send,
> interleaved N-ways under concurrency; and `probe_concurrency` sent one
> send PER token at every point, so M=1 at C>1 was NEVER probed. But the
> strong hypothesis — "one token cannot take concurrent sends, period" — is
> already FALSIFIED by banked data: Corner's default blast ran M=1 C=16 twice,
> 0 errors, on ~30 MB videos. ami_full's are 100–140 MB. The live variable is
> size x concurrency, not concurrency alone — which is why the probe's matrix
> carries the C16-small cell. What it is NOT, also from banked data: not
> resources, not ttl, not the container, not the corpus (the same files pass
> sequentially and on the LI arm).
>
> **Addendum, 2026-08-27 — second occurrence, new path, and this time the
> cause survived.** probe_frame_identity's `client.send()` of a 429.7 MB
> film hit the server's 250 MiB refusal (entry 24). The caller saw the same
> sentence as always — `ConnectionError('Could not send request')`,
> dap_client.py:229 — while the true cause (websockets'
> ConnectionClosedError quoting the server's 1009 close reason, WITH the
> exact byte arithmetic) survived only in the chained traceback: the
> wrapper raises without `from`, and the chain rode along as `__context__`.
> Two facts for the upstream ticket: the diagnostic the wrapper discards is
> SERVER-AUTHORED and names the number needed for the fix; and the
> information demonstrably exists at the raise site — `raise
> ConnectionError(...) from exc` is the whole repair. Second independent
> occurrence of the opacity (the first, above, cost two campaign nights and
> its true cause was never recovered); our probes now record the full
> exception chain themselves (probe_detect_text.exc_chain) rather than
> waiting on the SDK.

## 21. The dead default survived its own fix — entry 14 at the level of values (added 2026-08-26)

> Two legs died one night on the same defect wearing two lines. The driver
> grew multi-instance resolution (`--li-containers` → `args._svc_containers`),
> and the fix landed where the failure had been observed — the CPU bracket and
> collector — while `preflight_containers` 800 lines EARLIER kept
> running-checking `args.li_container`: the default name `li_video`, dead 21
> hours (H13). Fixed that site; the SAME night the weights check at another
> site read the same raw default and failed a healthy 8-instance set with
> `md5 None` (H12). Entry 14's mechanism exactly, one level down: there the
> stale thing was a duplicate COMPARATOR, here a stale VALUE — and both times
> the grep had been for the fix's shape, not for the operation ("who reads
> this name"). The cure is structural, not another patch: resolution moved
> BEFORE any name is used, and the raw attributes are then REPLACED with a
> sentinel (`_ConsumedContainerArg`) whose str/format/==/bool/hash all RAISE
> with a pointer to the resolved set — a third dead-default read is now a
> loud crash at the read site, plus a lint test asserting zero raw reads
> below the sentinel line. **When a value gains a resolved successor, the raw
> form must become unreadable, not merely unfashionable.** Multi-instance
> semantics were stated per site while routing: weights md5 = EVERY instance,
> refused on any mismatch by name (a mixed set is the failure the check
> exists for); declared thread env = must agree across the set; census and
> logs = instance 0 by stated convention.

## 22. The abort-before-write batch patch — one stale anchor silently discards the whole batch (added 2026-08-26)

> Three times in one session, a multi-patch edit script (N anchored
> replacements, each guarded by `assert old in s`, one `write_text` at the
> end) hit ONE stale anchor — an indent changed by an earlier refactor, a
> line Crossroad 41 had already rewritten — and the assert aborted the script
> AFTER several replacements had succeeded in memory and BEFORE anything was
> written. Net effect: the file unchanged, no error beyond a traceback that
> scrolled past, and the test suites GREEN — green because they were testing
> the untouched code. A checker cannot catch an edit that never happened.
> The failure mode is the mirror of entry 4's companion: not a failure
> wearing success's clothes, but a NO-OP wearing them. The cure used from
> then on: per-patch apply-and-report (an ok/MISS line per anchor, write the
> file regardless, then act on the MISSes), followed by a READ-BACK of the
> modified file's changed lines before the commit — never the memory of
> having edited.
>
> Beside it, the same session's process failure, recorded with its evidence:
> `990f827` was PUSHED while its own newly added test was red (the
> schema-service agreement test, failing on a paren-scan bug of its own);
> caught and fixed one commit later at `e158479`. The discipline is
> run-the-suite, READ the suite's output, then push — the run alone proves
> nothing if the output is not read, which is entry 9 (the reading is not the
> artifact) applied to one's own test results. Both rules are one rule:
> **an edit or a push is not done when the command returns; it is done when
> its effect has been read back.**

## 23. The working tree that edits itself — the rule existed, and a round was spent because it was filed where no reader would meet it (added 2026-08-26)

> Twelve tracked `.pipe` files in the team-repos clone read as locally
> modified — one-line JSON pretty-printed, +204/−21 lines — and the
> 2026-08-26 re-pin round recorded their origin as UNKNOWN, routed around
> them correctly (git-object reads for every pin), and filed a caveat. The
> origin was not unknown. It is a Phase 1 finding, on file the whole time:
> **a format-on-save daemon on this Mac rewrites `.pipe` files in the
> working tree**, and it once produced a false accusation that a teammate's
> committed pipe had drifted — his bytes were always correct; the tell was
> checking his git blob hash directly (PHASE1_CARRYOVER.md:465-468, item
> 10: "when a file disagrees with git, suspect your editor before
> suspecting the author"). The same machine behaviour at field level:
> SESSION_STATE.md:1742 — a pipe's `project_id` churns on save because an
> app rewrites it. Leela's team records the same churn on her side
> (team_docs_received/VIDEO-BENCHMARK-SETUP-2026-08-21.md:345 — DATA). The
> daemon itself remains unnamed; naming it is NOT a precondition for the
> rule, because the cure never touches the tree.
>
> **The rule, now filed where design reading starts: on this machine a
> working-tree read of any tracked `.pipe` — hash or content — is
> unciteable.** The citation surface is git objects only: `git show
> <sha>:<path>`, `git grep <pat> <sha>`, `git cat-file`. A checkout is not
> a read of a commit; it is an invitation for the environment to edit the
> commit's bytes before the read arrives. Entry 3's mechanism (a condition
> — an environment that mutates files — moved under the reading without a
> character of ours changing) wearing entry 9's clothes (the working tree
> is a rendering, not the artifact). The 2026-08-26 round applied the
> object-read rule from first principles, so nothing measured was wrong;
> what the round paid for was the DIAGNOSIS, re-derived from scratch,
> because the finding lived in a Phase 1 carryover appendix and not in this
> register — entry 7's mechanism one level up: the correction and the
> situation it corrects were kept in different places, aligned by nobody.
> A rule that is true but shelved where the surprised reader never stands
> is, operationally, a rule that does not exist. Consequence for tooling:
> any working-tree-dependent check on this machine (a dirty-tree gate, a
> hash comparison against a checkout) must either name and stop the daemon
> first, or be rewritten as an object read.

## 24. A 250 MiB ceiling, measured by refusal — and what it re-prices in DIAG_M1_BLAST (added 2026-08-27)

> The films frame-count check died in one message: the engine's websocket
> closed 1009 ('message too big') naming its own arithmetic — a
> 429,700,563-byte frame against a 262,144,000-byte limit. The frame was
> the 429,700,405-byte film plus 158 bytes of DAP envelope on this message:
> the transport sends raw binary (no base64), and the server refused it
> outright. The limit is pinned on BOTH sides: CONST_WEB_WS_MAX_SIZE =
> 250*1024*1024 (ai/constants.py:74), applied to the serving uvicorn at
> ai/web/server.py:458, and the same 250 MiB literal on the client for what
> IT receives (transport_websocket.py:384). Neither is env- or
> config-settable: changing either is an engine/SDK patch — a
> comparability deviation, not a knob.
>
> What it does NOT rewrite: DIAG_M1_BLAST had already named the constant
> and proved ~248 MB messages fit sequentially
> (DIAG_M1_BLAST_SOURCES.md:63-65); its loop-starvation reading of the
> C=16 deaths stands, and its "which side closed / true first exception"
> remains undetermined (dap_client ate it). What it DOES change: (1) the
> margin — ami_full's largest whole-video messages ran ~5% under a
> deterministic server refusal, so corpus sizing, not design, is what kept
> the whole-blob era alive; (2) on films the whole-blob send is dead at
> C=1 for any item larger than 262,143,842 bytes — at ~0.4 GB/h that is
> essentially the entire corpus — so the chunked write path is promoted
> from "measured 2.31% faster" to the ONLY admissible upload; (3) the
> class now has a measured discriminator: on any large-send 'Could not
> send request', the first check is payload+envelope vs 262,144,000. The
> engine's own remote node has chunked at 0.98 MiB for exactly this reason
> all along (nodes/remote/base/IInstance.py:301-303) — the limit was a
> recorded condition inside the engine and an unrecorded one in every
> client of send(). Kin: entry 3 (the condition was always there; the
> corpus moved out from under the code that was safe on it), entry 19 (a
> limit's unit of meaning — this one counts the MESSAGE, so no per-file
> reasoning saves you), entry 15 (a value right because of where it was
> written: send() was safe for the corpus it grew up on).

## 25. A flag lost in transit, caught by its read-back — and the pinned rebuild that moved 0.34% where unpinned moved 6% (added 2026-08-28)

> The anchor cell's first attempt lost `--network host` to SSM
> line-wrapping inside a long pasted block: all eight instances came up
> with NetworkMode='' and the driver's Crossroad-22 preflight REFUSED,
> naming the network mode it read back. Nothing was measured wrong,
> because the read-back existed — this is entry 3's shipped rule
> (`--network host` is a RECORDED, checked condition, never implied by the
> flag that requested it) collecting its first live save: the flag that
> requested the condition disappeared in transit, and the check that
> measures the condition did not care how it got lost. The transport
> failure itself is entry 9's shape one layer down — a pasted block is a
> RENDERING of a command, and a terminal that wraps or swallows a line
> does so without marking where. **Cure, standing: any long box block is a
> COMMITTED SCRIPT FILE plus its sha256, printed by the script itself at
> start and verified by the operator against the repo** — the first such
> file is probe/run_proof_layer2.sh. Paste stays acceptable only for
> short, single-purpose commands whose output is read.
>
> Paired, because the same anchor run produced it — **open item 3, strong
> evidence, not proof:** the LI image rebuilt with UNCHANGED code but the
> full 149-pin freeze install (the formerly UNPINNED service stack was the
> suspect surface) landed at 12.782 span f/s against the banked pair
> 12.745/12.733 — **0.34% from the banked mean, where the unpinned 25→26
> Aug rebuild had moved 6.0%** and within-build repro sits at 0.09%. One
> leg against an n=2 pair: consistent with "the unpinned install was the
> delta's surface, and the freeze closed it", and not yet proof of it —
> the counter-hypothesis (an unlucky 6% draw then, a lucky 0.34% draw now)
> is unlikely at 0.09% within-build repro but is not excluded by n=1.
> Ansh's phrasing adopted verbatim: strong evidence, not proof.

## 26. A box commit is landed only when the laptop has read it back from origin — and a cut bundle CLAIMS the base (ruled in 2026-08-28)

> The box committed d1b5ac3 (the proof-layer-1 artifacts) and bundled it to
> S3; the advisor's report said "box will bundle them" as if that were a
> landing, and the next round pushed four laptop commits onto the same base
> — 871e92e — before the bundle was fetched. The histories diverged and the
> box's `git pull --ff-only` refused, exactly as it should. Cause, honestly:
> **the advisor wrote "bundle when convenient" instead of marking it a
> stop-and-land step**, and the next prompt pushed onto the claimed base.
> Nothing was lost — the repair was a merge that landed the box side as-is
> after a mechanical path-overlap check (none) — but the repair existed
> only because both sides' history stayed unrewritten.
>
> The rule, ruled in verbatim: **a box commit is landed only when the
> bundle has been fetched into the laptop repo AND `git ls-remote origin`
> confirms the commit is reachable from the branch head, shas printed and
> compared.** Cut, uploaded, downloaded, even verified are not landed. And
> the corollary: **between a bundle being cut and its landing, the branch
> base is CLAIMED — no laptop work pushes onto that base until the box side
> is in.** The only permitted repair when the claim is violated is a merge
> that lands the box side as-is, after a mechanical path-overlap check
> (stop and report on any overlap rather than resolving unilaterally) —
> never a rebase, never a rewrite of the box's history. Kin: entry 22 (a
> push is done when its effect has been read back — this is that rule on
> the bundle path) and entry 25 (transport of commands; this is transport
> of COMMITS — a bundle in S3 is a rendering of history that nobody has
> read back yet).
>
> **Addendum, 2026-08-30 — second occurrence, other direction.** The box
> committed the films subset manifest (6b348c7) on 5a79dcd without pulling
> first, while origin was already at 8dc356d — the mirror image of the
> first incident (there the laptop pushed onto a claimed base; here the box
> worked on a stale one). The repair was identical and clean: mechanical
> overlap check (box touched only the manifest; NONE), merge as-is, push,
> ls-remote read back. The rule gains its operational other half: **the
> box pulls --ff-only BEFORE it works, and the wrapper's self-printed
> `repo HEAD` line is read at the STOP before anything measures** — a
> sweep run at a stale HEAD is a different instrument wearing the same
> command line.

## 27. A green self-test is a claim about the paths it ran — and the checker for the paths it cannot run existed, outside the loop (added 2026-08-30)

> The posture sweep died at all 11 points in ~15 minutes with zero
> artifacts: `NameError: name 're' is not defined` in
> probe_films_curve.py oom_state() — `re.search` in a module that never
> imported re. py_compile had passed (a parse proves nothing about
> names), and the same-day self-test had passed 20/20, because
> oom_state() is reachable ONLY from the live point path — it reads
> docker inspect and the container's memory.events — so no laptop
> self-test ever called it, and Python resolves a name when the line
> runs, not when the module loads. The suite's own OOM check exercised
> oom_delta (the arithmetic), never oom_state (the reader); the
> neighbouring module (probe_films_sizing.py:52) imports re beside an
> identical call shape — the pattern the eye fills in. The wrapper's
> record-and-continue held exactly as designed: 11 points, 11 honest
> failures, a summarize that said so. The box paid ~15 minutes for a
> name the laptop could have refused in milliseconds.
>
> **Third occurrence of the class.** Defect #36 — LI_CONTAINER undefined
> inside an if-EXTERNAL branch (smoke50_parser_in.py:978), survived every
> local run, detonated after 9,975 records; static_names.py was BUILT
> from it (its docstring, static_names.py:1-6; relayed this round as
> "#37", but #37 is the thread-pin defect per driver_video.py:24 — the
> file's own number stands here). Then the bare-python3 audit (as
> relayed). Now oom_state. Each time the name sat in code no local run
> executes — and that population is not random: **the functions whose
> first execution is on the box are exactly the functions whose names a
> self-test never resolves.** Entry 2 named the two independence
> crossings — execution, or an artifact the writing did not produce —
> and static_names.py IS the non-execution crossing for this class
> (symtable computes real scoping with nothing run). It existed the
> whole time as a separate step nobody ran: entry 7's mechanism (the
> correction and the thing it corrects kept in different places, aligned
> by nobody), at the level of checkers instead of commands.
>
> Cure, structural per entry 9's closing argument: **every probe's
> --self-test now runs the tree scan itself** —
> static_names.probe_selftest_findings(), one copy, called from all
> seven probes' suites — so "self-test PASS" can no longer be printed
> over an unresolvable name anywhere under working/video. The live
> defect served as the wiring's null control: the scan run BEFORE the
> fix, over 41 files, found exactly the sweep-killer and nothing else.
> Beside the broad fix, the narrow one: oom_state takes an injectable
> runner and the suite now EXECUTES its body on canned docker and
> memory.events shapes — the OOM instrument, ordered in so an OOM at
> 32x1 would be a FINDING, was itself the only unmeasured instrument in
> the file (entry 12: the read-back is half of the measurement). Kin to
> entry 22, which is the whole lesson in one line: an edit or a push is
> done when its EFFECT has been read back — a green suite is the
> command's success, not the effect, and the effect includes the paths
> the suite structurally cannot take, which is precisely where a
> second, non-execution instrument must stand.
>
> **Addendum, same day — the second bug in the same file was the same
> lesson one layer deeper.** `--summarize`, run for the first time over
> REAL artifacts (the completed 11/11 posture matrix), died on
> KeyError('n_films'): `_point_row` read a top-level key the producer
> has NEVER written — `n_films` has lived inside point_metrics' return
> since the file's first commit (d73f445), so the reader was born
> disagreeing with the writer, and the fixture added at 21c6ff2 was
> hand-shaped to match the READER, so 23 green checks certified the
> defect. The morning's name scan was clean — every name resolved; the
> SHAPE was wrong, and no name checker sees shapes. A hand-written
> fixture is entry 2's self-copy INSIDE the test: the author's memory
> of the schema sampled against the author's code, and no such sample
> can catch the fabrication. Cure, one copy per entry 6's addendum: the
> artifact shape now has ONE producer (build_point_artifact /
> build_failed_artifact), main() writes through it, and the self-test
> builds its fixtures through the same functions with point_metrics
> feeding them — producer and formatter tested as one chain, so a
> schema change breaks a test instead of a matrix. Honest boundary kept
> per the operator's instruction: an artifact that cannot report
> n_films prints SATURATION-NOT-KNOWN — never computed from a guess,
> and never conflated with NEVER-SATURATED (the old two-state print
> would have mislabelled None as never-saturated).
>
> **Third addendum (2026-09-02) — the fourth shape defect moved from the
> FIELD to the CHANNEL.** The detector-parity side docs travelled over
> STDOUT, and the engine's embedded interpreter (the engine executable
> itself) prints its own banner to stdout — so the captured "JSON"
> arrived with a prefix and --compare crashed on the fourth
> producer/consumer contract break of the campaign (n_films' nesting,
> saturated's two questions, frame_labels' wire-vs-record name, and now
> a data artifact routed through a stream another writer shares). The
> fix belongs in the ARGUMENT CONTRACT, not the parser: a probe's data
> artifact travels as a FILE at an explicit path (--side-out, refused
> absent), because a shared stream is a rendering, not an artifact
> (entry 9); and the consumer's parse failure names the file and its
> first bytes (entry 15: name what you looked at). Kin to the whole
> entry: stdout pollution from the embedded interpreter is exactly a
> property only a live box exhibits — no laptop test prints that
> banner.
>
> **Second addendum (2026-08-31) — the cure does not transfer by having
> written it.** The very next new reader of driver records
> (derive_gate3_arming.py, written days AFTER this addendum by its own
> author) hand-built its fixtures again — under the WIRE schema's field
> name (`frame_labels`, schema.py) instead of the RECORD's
> (`frame_label_multisets`, record_from_rr/record_from_li) — and its
> green 7/7 suite certified a reader that refused every real staged
> record ("carries no frame_labels", 2026-08-31; third occurrence:
> n_films, saturated's two questions, now this). The rule gains its
> operational half: **producer-built fixtures are a rule about WRITING
> new readers, not about fixing old ones** — every reader of a produced
> shape starts life with its fixtures built through the producer
> (record_from_li on a canned wire body, here) and with a null control
> in the exact shape of the last miss (a record wearing the wire name
> must be REFUSED naming sought + actual keys). Both now in the
> deriver's suite. The campaign's own cross path was verified correct
> (driver_video.py:1705-1707 reads the record names) — the driver reads
> its own records; only the fresh outside reader guessed.

## 28. Two correct predicates, one of them the wrong question (added 2026-08-31; diagnosis accepted and ordered recorded by Ansh)

> When the C sweep ran C=16/32 on a 9-film batch, the summarizer's
> `saturated` flag read TRUE — and it was RIGHT. Its predicate,
> `inflight_max >= min(C, n_films)`, answers "did the point reach the
> batch's achievable bound", and the points did: nine films, nine
> in-flight. The marginal chain then divided by REQUESTED C and printed
> efficiency rows for concurrency that never happened, and the flag that
> existed to catch saturation problems could not object — because nobody
> had asked it the question the arithmetic depended on: "did the point
> run at its requested C" (`inflight_max >= C`). Both predicates are
> correct; they answer different questions; the computation consulted
> the wrong one.
>
> This is a DISTINCT failure shape from a wrong predicate (entry 10's
> census, entry 8's presence-guard) and from a proxy for the right
> quantity (entries 3 and 18): nothing here was broken or proxied — the
> system carried a TRUE answer to a question nobody was asking, and the
> true answer read as clearance for arithmetic it did not license.
> Nearest kin is entry 17 (two instruments, two quantities, one name),
> moved inside a single artifact: 'saturated' was one word wearing two
> meanings — batch-bound-reached vs requested-C-realized — and each
> reader took whichever meaning their sentence needed. The cure, as
> shipped with the 2026-08-31 realization gate: give each question its
> own NAMED predicate (`_c_realized` beside `saturated`), make every
> computation consult the one it depends on, and print both questions'
> raw inputs beside the verdict (`inflight_max` and `n_films` now ride
> every row) so a reader can see which question any flag answers. The
> rule: **before trusting a guard, state in words the question it
> answers and compare that with the question the computation needs
> answered — a TRUE flag licenses nothing but its own question.**

## 29. The ceiling was measured, the rule was written, and the unconverted path waited for the next reader (added 2026-08-31)

> Films staging died at the golden write: smoke_video._send_video still
> carried client.send(token, video.read_bytes()) — ONE whole-blob DAP
> message — and the shortest measured film is 527.3 MiB against the
> 262,144,000-byte ceiling entry 24 measured BY REFUSAL days earlier.
> Entry 24 wrote the rule ("chunked writes are the ONLY admissible
> upload") and re-priced the class; what it did not order was the AUDIT:
> enumerate every send() call site and convert, guard, or quarantine
> each. The driver was converted (58f2bb3); the smoke — a path only a
> live box reaches, exercised only when a campaign runs — was not, and
> no campaign ran between the conversion and today. Third instance of
> the class "a path only a live box reaches was never converted / never
> checked": oom_state's import re (entry 27), the bare-python3 audit (as
> relayed), now the golden send.
>
> Same incident, one layer down, same shape: the SDK static scan blocked
> staging with three "client.pipe() not in the verified surface" fails —
> and the scanner was RIGHT to block. pipe() is real (dev-checkout
> signature engine/rocketride/mixins/data.py:368-370; executed on the
> installed wheel by the detect-text probe on a 429.7 MB film and by 31
> sweep points), but the surface list froze at d5a32f5, pipe() entered
> at 58f2bb3 three days later, and scan_tree's only caller is the smoke
> — which never ran between the two. A checker wired to a path that
> stopped running is a checker outside the loop (entries 7 and 27's
> mechanism); it fired the moment the path ran again — the system
> working, LATE. The surface was extended WITH its evidence, never to
> silence the gate.
>
> The failure also exercised an untested failure path: terminate ran
> against a dead connection and raised AttributeError, so the log's
> loudest line was corpse-handling, not the cause (which rode
> __context__ per entry 20 and went unprinted). The golden path now
> reports the full exception chain AT the send failure, skips terminate
> on a dead connection and says so, and states the leak bound: a golden
> task's ttl 3600 is an IDLE timer (entry 19), so an unterminated task
> reaps inside the >=2.5 h LI block or dies with the container teardown
> — no collision with measured legs in any built sequence, and a failed
> golden kills the plan before legs exist (fail-closed run()).
>
> The audit entry 24 should have ordered, performed today — every
> client.send() site, classified by max plausible payload: smoke golden
> (CONVERTED — the one import of the one proven loop, entry 6); driver
> envprobe (a ~13-byte string; safe); probe_transport_cost (AMI
> whole-vs-chunked comparator — now REFUSES blobs over the ceiling
> rather than measuring a refusal as a timing); probe_frame_identity
> (the ceiling's discovery instrument, superseded, quarantine-noted);
> probe_m1_concurrency and probe_rr floor sends (AMI-era diagnostics,
> AMI-sized payloads, on no films path); the Phase-1 scripts tree
> (text/PDF, KB-MB, out of scope). The rule the class keeps teaching:
> **a measured limit is not absorbed when the rule is written; it is
> absorbed when every path that can hit it has been enumerated and each
> one converted, guarded, or quarantined — the audit is part of the
> finding, not a follow-up** (entry 6's consumer-grep rule, at the
> level of transport).

## 30. A probe that was not like-for-like — caught by its own artifact, not by anyone's memory (added 2026-09-03)

> The side test's v2 run compared the two containers' detector paths and
> found them bit-equal — with the thread state of neither side recorded.
> The design had called for `torch.get_num_threads()` in the side doc;
> v2 omitted it, and the omission was owned in the read-back. The fields
> were added before the Ruling-Y run. Run 1's engine side then reported,
> in its own output: intraop 16, interop 16, all six BLAS/OMP variables
> null — **the standalone default, not the campaign's six-vars=2
> posture**. Nobody remembered this; nobody had to. The artifact said it.
>
> The catch changed the experiment. A single-condition run would have
> compared the stacks under thread state unlike the campaign's on both
> sides, and any verdict would have carried an unstated assumption. The
> redesign ran BOTH conditions — the default, preserving comparability
> with v2, and the campaign's pinning (all six vars = 2 through the same
> per-container mechanism the legs used) — with restated pre-registered
> verdicts. The result (bit-equal in every cell, on a frame production
> recorded as diverging) thereby excluded thread count as a standalone
> mechanism INSTEAD of merely not testing it: the recording doubled the
> strength of the finding (Ruling Y verdict, films DEFINITIVE §6;
> Ansh's crediting ruling, 2026-09-03: the T2 condition was the
> implementation side's addition after spotting the mismatch in the
> engine side's own output).
>
> The rule: **a diagnostic probe records, inside its result artifact,
> every execution condition its comparison depends on — and
> like-for-like is established by READING those fields, never by
> assuming the run inherited the posture someone intended.** A probe
> whose conditions went unrecorded supports no like-for-like claim; a
> probe that records them turns its own first mis-posed run into the
> discovery that re-poses it. (Entry 25's read-back principle, applied
> to instruments: the read-back is half the measurement — here it was
> the half that saved the other half.)

## 31. A measured absence, unapplied at the site that needed it — and a new tool with no startup check (added 2026-09-04)

> The box has no host ffmpeg and no ffprobe; imageio_ffmpeg's bundled
> binary is the only decode path. That absence was measured long ago and
> is written into the campaign's PRACTICE everywhere — every probe and
> fetch tool resolves `imageio_ffmpeg.get_ffmpeg_exe()` precisely because
> nothing else exists. Then the 500-manifest builder gained a
> width/height feature that called `ffprobe` beside the bundled ffmpeg,
> and the run failed 500 times out of 500 — including on films with
> committed byte-parity artifacts — before being killed. The uniformity
> was the tell (Ansh's diagnosis, confirmed from the binaries dir): a
> codec problem is partial; a 100% failure spanning known-good files is a
> missing binary.
>
> Two defects, both process: (1) a recorded fact was not applied at the
> site that needed it — kin to entry 23, where the rule existed but lived
> where the surprised reader never stands; here the fact lived in
> practice and in memory, and the NEW code was written as if on a machine
> with ffprobe. (2) The campaign's own convention is that a new tool
> dependency gets a STARTUP check — this one had none, so the impossible
> call burned through 300 films repeating itself instead of refusing once
> with the tool named.
>
> The rules: **new code inherits the environment's measured absences,
> not the author's home machine; and every new tool dependency refuses at
> startup, by name, before the first item is attempted.** The fix (v2)
> also collected the masked debt: the null control on the 35 knowns —
> the entire reason to trust the 500 manifest — had never executed once,
> and now runs as its own gated pre-step (KNOWNS_ONLY=1) before the 500
> are attempted. Replacement mechanism proven before adoption: the pinned
> package's own header meta (read_frames first yield) matched the
> committed census exactly on three knowns spanning the 560px edge.

## 32. A comparator that keeps talking after its own refusal — second instance, and the derived-selector class beneath it (added 2026-09-04)

> The films-500 staging smoke compared the golden against the WRONG film
> — its golden video was DERIVED ("shortest measured item"), and the
> corpus change moved the answer (35-corpus: HouseOnBareMountain; the
> 500-corpus: ACloseCallForBostonBlackie). The sha check caught the
> mismatch and said so. Then the instrument kept going: it diffed the
> two films' chunk lists anyway and printed "this is a REGRESSION, not a
> configuration drift" — a conclusion drawn PAST its own refusal. Entry
> 14 states the discipline (a comparator that cannot prove same-input
> has not found a difference); this campaign has now produced two
> instruments that implemented the check and continued past it: the
> films cross-gate printed FAIL while the same-frames premise was still
> unproven (resolved by measurement and Ruling U — the verdict happened
> to survive), and now the golden compare printed REGRESSION on
> different inputs (the verdict was nonsense). The rule the recurrence
> adds to entry 14: **the same-input gate is extracted as its own
> function, the caller RETURNS at its refusal, and a null control
> asserts both that the refusal fires on mismatched inputs naming BOTH
> shas and that no downstream verdict text can be emitted with it** —
> implemented in smoke_video.golden_same_input + its null control, which
> runs on every smoke.
>
> Beneath it, the week's third derived-selector bite (warm pair; golden
> film; and the ffprobe absence as kin): **a value that must match a
> corpus is either pinned to a committed artifact or derived at run time
> from one, refuse-if-absent — never derived from a property ("shortest",
> "last two") of a thing that can move.** The golden now pins itself: in
> compare mode the film comes FROM the golden record's own video field,
> the manifest sha is checked against the golden's recorded sha BEFORE
> the two-minute send, and the shortest-item selector survives only in
> write mode, where it records its choice into the artifact it creates.
