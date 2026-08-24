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
