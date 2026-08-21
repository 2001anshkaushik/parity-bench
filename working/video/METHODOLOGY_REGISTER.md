# Methodology register — DRAFT (placement is Ansh's, per the 2026-08-20 ruling)

Two entries, one lesson from two directions (operator's framing, 2026-08-21).
Entry 1 is reproduced VERBATIM from the session record where it was drafted —
recovered from the transcript rather than rewritten from memory, which is
entry 2's point in miniature.

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
