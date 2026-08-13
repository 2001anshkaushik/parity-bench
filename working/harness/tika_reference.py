"""Independent RocketRide parse reference — the engine's own Tika, run outside the engine.

WHY THIS EXISTS
---------------
A parse gate needs a reference that can *falsify* the parser under test. Two candidates fail:

* **The engine's own captured output** (the shape §4.3 of the team spec uses) is self-referential.
  Any DETERMINISTIC defect is reproduced identically by every later run, so the gate agrees with
  itself and reports 100 %. Measured on our NUL-truncation defect: a self-capture gate passes 3/3
  while an independent reference fails, naming the offset. 100 % agreement on 100 % data loss.
* **pypdf** would make every legitimate Tika/pypdf difference look like a defect. Leela rejected
  this correctly.

This module takes the third option: run **the engine's own Tika 3.2.3**, from the engine's own jars,
with the engine's own `tika-config.xml`, in a **separate process**. Independent of the thing under
test, but the same parser — so differences are defects, not parser disagreement.

THE EXACT RULE  [VERIFIED — 8/8 documents byte-exact, sha256 equality]
---------------------------------------------------------------------
    engine_parse_text == standalone_tika(pdf, engine/java/tika-config.xml) + "\\n\\n"

The engine appends exactly two trailing newlines to Tika's output. The rule is ASSERTED rather than
assumed: if the engine stops appending them the gate fails loudly on every document and the rule is
re-derived. That is the correct failure mode — a normalising comparison would instead hide the
truncation defects this gate exists to catch.

⚠️ Measured on engine **3.3.1.35** only. **Re-derive on 3.2.1 before relying on it.**

⚠️ `tika-config.xml` is not optional: it EXCLUDES TesseractOCRParser, OOXMLParser, OfficeParser and
GDALParser from DefaultParser. A reference built without it is a different parser.

BUILD CONSTRAINT
----------------
The engine bundles a **JRE, not a JDK**: there is no `javac`, and `java`'s single-file source mode
fails with `Module jdk.compiler not in boot Layer`. Compile `TikaExtract.java` once with any JDK 17
against the engine's jars, ship the `.class`, and RUN it on the bundled JRE. Example:

    docker run --rm -v "$PWD/engine/java/lib:/jars:ro" -v "$PWD/working/tika:/work" -w /work \\
      eclipse-temurin:17-jdk sh -c 'javac -cp "/jars/*" -d /work TikaExtract.java'
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
JRE = ROOT / "engine" / "java" / "jre" / "bin" / "java"
JARS = ROOT / "engine" / "java" / "lib"
CONFIG = ROOT / "engine" / "java" / "tika-config.xml"
CLASSDIR = ROOT / "working" / "tika"

ENGINE_SUFFIX = "\n\n"          # measured, 8/8 byte-exact on engine 3.3.1.35


class TikaReferenceUnavailable(RuntimeError):
    """The standalone extractor is not built, or the bundled JRE is missing."""


def available() -> tuple[bool, str]:
    """Can we build a reference at all? Returns (ok, reason)."""
    if not JRE.exists():
        return False, f"bundled JRE not found at {JRE} — provision the engine (PROVISIONING.md §1)"
    if not (CLASSDIR / "TikaExtract.class").exists():
        return False, (f"{CLASSDIR}/TikaExtract.class not built. The bundle ships a JRE, not a JDK; "
                       f"compile once with any JDK 17 against {JARS} — see the module docstring.")
    if not CONFIG.exists():
        return False, f"engine tika-config.xml not found at {CONFIG} — the reference would use a "
    return True, "ok"


def standalone_text(pdf: Path, timeout: float = 300.0) -> str:
    """Extract with the engine's Tika, in a separate process. Raises if unavailable."""
    ok, why = available()
    if not ok:
        raise TikaReferenceUnavailable(why)
    r = subprocess.run(
        [str(JRE), "-cp", f"{CLASSDIR}:{JARS}/*", "TikaExtract", str(pdf), str(CONFIG)],
        capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise TikaReferenceUnavailable(
            f"standalone Tika failed on {pdf.name}: {r.stderr.decode('utf-8', 'replace')[:300]}")
    return r.stdout.decode("utf-8", "replace")


def reference_text(pdf: Path) -> str:
    """The text the ENGINE should return for this PDF, built independently of the engine."""
    return standalone_text(pdf) + ENGINE_SUFFIX


def verify_rule(pdfs, engine_text_fn, n: int = 8) -> dict:
    """Null control for the reference itself: does the rule still hold on clean documents?

    Run this before trusting any gate built on it, and re-run it after any engine upgrade. If the
    rule has drifted, every gate result built on it is wrong — so this must fail loudly rather than
    quietly normalising the difference away.
    """
    rows, exact = [], 0
    for pdf in list(pdfs)[:n]:
        eng = engine_text_fn(pdf)
        ref = reference_text(Path(pdf))
        match = eng == ref
        exact += match
        rows.append({"doc": Path(pdf).name, "exact": match,
                     "engine_chars": len(eng), "reference_chars": len(ref)})
    return {"rule": "standalone_tika(pdf, engine tika-config.xml) + '\\n\\n'",
            "exact_matches": exact, "n": len(rows), "holds": exact == len(rows), "rows": rows,
            "note": "measured on engine 3.3.1.35; MUST be re-derived on any other engine build"}
