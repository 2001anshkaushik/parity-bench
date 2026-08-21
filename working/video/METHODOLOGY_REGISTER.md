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
