#!/usr/bin/env python3
"""Framework verification — produce an evidence-backed dossier per candidate framework.

Purpose
-------
We established RocketRide's architecture by reading its source: work-stealing pool at
`ThreadedQueue.hpp:48`, per-task process trees, MIT licence, embedded Python 3.12. Every
competitor needs the same standard of evidence before it appears in a published chart. This
script mechanises that, so no claim in the final report rests on recollection.

For each framework it establishes, from primary sources only:
  1. Does the package exist on PyPI, and under what exact name and version?
  2. What licence, and does it permit publishing benchmark results?
  3. Where is the source, and can we read it?
  4. Does it execute **locally**, or is it a client for a hosted API? (Track A eligibility)
  5. What concurrency primitives does its own code use?
  6. Does it sit on top of another framework under test? (independence disclosure)

Anything it cannot verify is recorded as "UNVERIFIED" — never inferred.

Usage:
    python scripts/verify_frameworks.py                 # all defaults
    python scripts/verify_frameworks.py --install       # also try an isolated install + import
    python scripts/verify_frameworks.py langgraph crewai
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOSSIER_DIR = ROOT / "dossiers"
UV = Path.home() / ".local" / "bin" / "uv"

# Candidate name -> plausible PyPI distribution names, most likely first.
# Multiple candidates because marketing names and distribution names frequently differ; we let
# the registry decide rather than guessing.
CANDIDATES: dict[str, list[str]] = {
    "langgraph":  ["langgraph"],
    "crewai":     ["crewai"],
    "deepagents": ["deepagents"],
    "lyzr":       ["lyzr", "lyzr-agent-api", "lyzr-automata"],
    "omnigent":   ["omnigent", "databricks-omnigent", "databricks-agents", "databricks-langchain"],
    "llamaindex": ["llama-index-core"],
    "autogen":    ["autogen-agentchat", "pyautogen"],
    "ray":        ["ray"],
    "dask":       ["dask"],
    "prefect":    ["prefect"],
}

# Evidence that a package is primarily a client for a remote service rather than a local runtime.
HOSTED_MARKERS = [
    r"https?://[a-zA-Z0-9.\-]+\.[a-z]{2,}",
]

# Domains that say NOTHING about whether orchestration is local.
#
# The first version of this classifier declared LangGraph "HOSTED_API" on the strength of
# `https://api.myauth-provider.com` — a placeholder in a docstring — and CrewAI on the strength of
# `api.openai.com`. Every agent framework calls an LLM provider; that is what the frameworks are
# *for*, and it is orthogonal to where the graph executes. Conflating "talks to a model API" with
# "runs on the vendor's cloud" would have wrongly excluded the two most important competitors from
# Track A, which is the mirror image of the strawman error and just as disqualifying.
LLM_PROVIDER_DOMAINS = {
    "api.openai.com", "api.anthropic.com", "api.groq.com", "api.cerebras.ai",
    "api.mistral.ai", "api.cohere.ai", "api.together.xyz", "api.deepseek.com",
    "generativelanguage.googleapis.com", "api.perplexity.ai", "openrouter.ai",
    "api.voyageai.com", "api.x.ai", "api.fireworks.ai", "huggingface.co",
    "api-inference.huggingface.co", "api.endpoints.anyscale.com",
}
PLACEHOLDER_DOMAINS = {
    "api.example.com", "example.com", "api.myauth-provider.com", "api.weather.com",
    "api.your-service.com", "localhost", "127.0.0.1", "api.github.com",
    "schema.org", "www.w3.org", "json-schema.org", "api.islo.dev",
}
INFRA_DOMAINS = {
    "pypi.org", "python.org", "readthedocs.io", "githubusercontent.com",
    "opentelemetry.io", "www.apache.org", "creativecommons.org",
}
_DOMAIN_RE = re.compile(r"https?://([a-zA-Z0-9.\-]+)")
CONCURRENCY_MARKERS = {
    "asyncio": r"\bimport asyncio\b|\basync def\b",
    "threading": r"\bimport threading\b|\bThread\(",
    "multiprocessing": r"\bimport multiprocessing\b|\bProcessPoolExecutor\b",
    "thread_pool": r"\bThreadPoolExecutor\b",
    "ray": r"\bimport ray\b",
    "celery": r"\bfrom celery\b|\bimport celery\b",
}
PERMISSIVE = {"MIT", "APACHE", "BSD", "ISC", "MPL", "PSF"}


@dataclass
class Dossier:
    candidate: str
    resolved_name: str | None = None
    exists_on_pypi: bool = False
    version: str | None = None
    author: str | None = None
    last_release_date: str | None = None
    days_since_last_release: int | None = None
    release_count: int | None = None
    maintenance_status: str = "UNVERIFIED"   # ACTIVE | STALE | ABANDONED
    requires_python: str | None = None
    license: str | None = None
    license_permissive: str = "UNVERIFIED"
    summary: str | None = None
    source_repo: str | None = None
    homepage: str | None = None
    dependencies: list[str] = field(default_factory=list)
    depends_on_frameworks_under_test: list[str] = field(default_factory=list)
    install_ok: str = "NOT_ATTEMPTED"
    install_error: str | None = None
    import_ok: str = "NOT_ATTEMPTED"
    installed_version: str | None = None
    execution_locality: str = "UNVERIFIED"   # LOCAL | HOSTED_API | HYBRID | UNVERIFIED
    hosted_evidence: list[str] = field(default_factory=list)
    telemetry_endpoints: list[str] = field(default_factory=list)
    concurrency_primitives: list[str] = field(default_factory=list)
    track_a_eligible: str = "UNVERIFIED"     # execution-substrate comparison
    track_b_eligible: str = "UNVERIFIED"     # orchestration-overhead comparison
    notes: list[str] = field(default_factory=list)
    tried_names: list[str] = field(default_factory=list)


def pypi_metadata(name: str, timeout: float = 12.0) -> dict | None:
    url = f"https://pypi.org/pypi/{name}/json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "rocketride-bench-verify/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def _find_repo(info: dict) -> str | None:
    urls = info.get("project_urls") or {}
    for key in ("Source", "Source Code", "Repository", "Homepage", "Code", "GitHub"):
        for k, v in urls.items():
            if k.lower() == key.lower() and v:
                return v
    for v in urls.values():
        if v and "github.com" in v:
            return v
    return info.get("home_page") or None


def _license_of(info: dict) -> str | None:
    lic = info.get("license")
    if lic and len(lic) < 200:
        return lic.strip()
    for c in info.get("classifiers", []):
        if c.startswith("License ::"):
            return c.split("::")[-1].strip()
    le = info.get("license_expression")
    return le.strip() if le else None


def _is_vendor_endpoint(domain: str, vendor_tokens: set[str]) -> bool:
    """True only for the *vendor's own* control plane — not model providers, not placeholders.

    A vendor control-plane endpoint is real evidence that orchestration may happen remotely. An
    LLM endpoint is evidence of nothing. This distinction is the whole point of the function.
    """
    d = domain.lower()
    if d in LLM_PROVIDER_DOMAINS or d in PLACEHOLDER_DOMAINS or d in INFRA_DOMAINS:
        return False
    if any(d.endswith(suffix) for suffix in INFRA_DOMAINS):
        return False
    return any(tok in d for tok in vendor_tokens if len(tok) >= 4)


def scan_installed_source(site_dir: Path, pkg_hint: str,
                          vendor_tokens: set[str] | None = None) -> tuple[list[str], list[str]]:
    """Grep an installed package's own source for hosted-API and concurrency evidence."""
    hosted: list[str] = []
    concurrency: set[str] = set()
    vendor_tokens = vendor_tokens or {pkg_hint.split("-")[0].lower()}
    hint = pkg_hint.split("-")[0][:6].lower()
    roots = [p for p in site_dir.glob("*") if p.is_dir() and hint in p.name.lower()]
    if not roots:
        roots = [p for p in site_dir.glob("*") if p.is_dir() and not p.name.endswith(".dist-info")]
    files: list[Path] = []
    for r in roots[:6]:
        files.extend(list(r.rglob("*.py"))[:400])
    for f in files[:1200]:
        try:
            txt = f.read_text(errors="ignore")
        except Exception:
            continue
        for m in _DOMAIN_RE.findall(txt):
            if _is_vendor_endpoint(m, vendor_tokens) and m not in hosted:
                hosted.append(m)
        for label, pat in CONCURRENCY_MARKERS.items():
            if re.search(pat, txt):
                concurrency.add(label)
    return hosted[:15], sorted(concurrency)


def try_install(dist: str, dossier: Dossier) -> None:
    """Install into a disposable venv and introspect. Never touches the benchmark venv."""
    if not UV.exists():
        dossier.install_ok = "SKIPPED"
        dossier.install_error = f"uv not found at {UV}"
        return
    tmp = Path(tempfile.mkdtemp(prefix=f"verify-{dist}-"))
    try:
        r = subprocess.run([str(UV), "venv", "--python", "3.12", str(tmp / "v")],
                           capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            dossier.install_ok = "FAIL"
            dossier.install_error = (r.stderr or r.stdout)[-500:]
            return
        py = tmp / "v" / "bin" / "python"
        r = subprocess.run([str(UV), "pip", "install", "--python", str(py), dist],
                           capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            dossier.install_ok = "FAIL"
            dossier.install_error = (r.stderr or r.stdout)[-800:]
            return
        dossier.install_ok = "OK"

        # Distribution name != import name for namespaced packages: `llama-index-core`
        # installs as `llama_index.core`, not `llama_index_core`. Deriving the module by naive
        # dash->underscore reported a false ModuleNotFoundError. Try the plausible spellings.
        flat = dist.replace("-", "_")
        cands = [flat]
        if flat.count("_") >= 1:
            head, _, tail = flat.partition("_")
            cands.append(f"{head}_{tail.replace('_', '.', 1)}" if "_" in tail else flat)
            parts = flat.split("_")
            cands.append(parts[0] + "_" + parts[1] + "." + ".".join(parts[2:]) if len(parts) > 2 else flat)
            cands.append(".".join(parts))
        mod = flat
        probe = (
            "import importlib, importlib.metadata as md, json\n"
            f"name={dist!r}; mod={mod!r}; cands={cands!r}\n"
            "out={}\n"
            "try:\n"
            "    out['version']=md.version(name)\n"
            "except Exception:\n"
            "    out['version']=None\n"
            "try:\n"
            "    m=None; err=None\n"
            "    for cand in cands:\n"
            "        try:\n"
            "            m=importlib.import_module(cand); out['import_module']=cand; break\n"
            "        except Exception as e:\n"
            "            err=type(e).__name__+': '+str(e)[:120]\n"
            "    if m is None: raise RuntimeError(err or 'no candidate imported')\n"
            "    out['import']='OK'\n"
            "    out['symbols']=len([s for s in dir(m) if not s.startswith('_')])\n"
            "except Exception as e:\n"
            "    out['import']='FAIL: '+type(e).__name__+': '+str(e)[:200]\n"
            "print(json.dumps(out))\n"
        )
        r = subprocess.run([str(py), "-c", probe], capture_output=True, text=True, timeout=300)
        if r.returncode == 0 and r.stdout.strip():
            try:
                data = json.loads(r.stdout.strip().splitlines()[-1])
                dossier.import_ok = data.get("import", "UNKNOWN")
                dossier.installed_version = data.get("version")
            except Exception:
                dossier.import_ok = "PARSE_FAIL"
        else:
            dossier.import_ok = f"FAIL: {(r.stderr or '')[-200:]}"

        site = next((tmp / "v" / "lib").glob("python3.*/site-packages"), None)
        if site:
            vendor_tokens = {dist.split("-")[0].lower(), dossier.candidate.lower()}
            hosted, conc = scan_installed_source(site, dist, vendor_tokens)
            dossier.hosted_evidence = hosted
            dossier.concurrency_primitives = conc
    except subprocess.TimeoutExpired:
        dossier.install_ok = "TIMEOUT"
    except Exception as e:
        dossier.install_ok = "ERROR"
        dossier.install_error = repr(e)[:400]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


TELEMETRY_TOKENS = ("telemetry", "analytics", "tracking", "segment", "posthog", "mixpanel")

# Documented opt-outs, applied to every run so no framework pays a network tax the others do not.
TELEMETRY_OPT_OUTS = {
    "crewai": ["CREWAI_DISABLE_TELEMETRY=true", "OTEL_SDK_DISABLED=true"],
    "omnigent": ["OTEL_SDK_DISABLED=true", "DO_NOT_TRACK=1"],
    "langgraph": ["LANGCHAIN_TRACING_V2=false", "LANGSMITH_TRACING=false"],
    "deepagents": ["LANGCHAIN_TRACING_V2=false", "LANGSMITH_TRACING=false"],
}


def detect_telemetry(d: Dossier) -> None:
    """Flag phone-home endpoints and the env vars that silence them.

    Background telemetry is a live benchmark hazard, not a privacy footnote: an HTTP POST on a
    background thread during a timed run adds latency, variance and memory that belong to the
    vendor's analytics, not to their scheduler. If one framework phones home and another does not,
    the comparison is measuring network conditions. Every opt-out below is applied uniformly and
    recorded in the run's environment block so reviewers can see it was done.
    """
    hits = [h for h in d.hosted_evidence if any(t in h.lower() for t in TELEMETRY_TOKENS)]
    if hits:
        d.telemetry_endpoints = hits
        opts = TELEMETRY_OPT_OUTS.get(d.candidate, ["OTEL_SDK_DISABLED=true", "DO_NOT_TRACK=1"])
        d.notes.append(
            f"Phones home to {', '.join(hits)} by default. Set {', '.join(opts)} for every run "
            "and record it in the environment block, or the measurement includes their analytics "
            "traffic."
        )


def classify(d: Dossier) -> None:
    """Decide track eligibility from evidence only.

    Text evidence can suggest a hosted control plane but must never *settle* it — the decisive
    test is behavioural: can a trivial pipeline execute locally with no credentials and no
    network? That probe is framework-specific and belongs with the Phase 2 adapters, so this
    function deliberately stops at LIKELY_LOCAL / REVIEW_REQUIRED and marks the probe outstanding.
    Asserting a verdict the evidence does not support is the failure mode this whole script exists
    to prevent, and it applies to verdicts against competitors just as much as for them.
    """
    if d.hosted_evidence:
        d.execution_locality = "REVIEW_REQUIRED"
    elif d.install_ok == "OK" and d.import_ok == "OK":
        d.execution_locality = "LIKELY_LOCAL"

    if d.license:
        up = d.license.upper()
        d.license_permissive = "YES" if any(p in up for p in PERMISSIVE) else "REVIEW_REQUIRED"

    if not d.exists_on_pypi:
        d.track_a_eligible = d.track_b_eligible = "NO — package not found on PyPI"
        return
    if d.install_ok == "FAIL":
        d.track_a_eligible = "NO — does not install on Python 3.12"
        d.track_b_eligible = "NO — does not install on Python 3.12"
    elif d.execution_locality == "REVIEW_REQUIRED":
        d.track_a_eligible = "PENDING — vendor endpoint found; behavioural probe required"
        d.track_b_eligible = "PENDING — vendor endpoint found; behavioural probe required"
    elif d.execution_locality == "LIKELY_LOCAL":
        d.track_a_eligible = "LIKELY — confirm with offline behavioural probe"
        d.track_b_eligible = "LIKELY — confirm with offline behavioural probe"
    else:
        d.track_a_eligible = "UNVERIFIED — run with --install"
        d.track_b_eligible = "UNVERIFIED — run with --install"
    if d.maintenance_status == "ABANDONED":
        d.track_a_eligible = "NO — unmaintained; would misrepresent the vendor's current product"
        d.track_b_eligible = "NO — unmaintained; would misrepresent the vendor's current product"

    if d.depends_on_frameworks_under_test:
        d.notes.append(
            "Shares a substrate with another framework under test "
            f"({', '.join(d.depends_on_frameworks_under_test)}) — results are NOT independent "
            "and must be disclosed as such."
        )


def build_dossier(candidate: str, names: list[str], do_install: bool) -> Dossier:
    d = Dossier(candidate=candidate, tried_names=names)
    info = None
    meta_full = None
    for n in names:
        try:
            meta = pypi_metadata(n)
        except Exception as e:
            d.notes.append(f"PyPI lookup failed for {n}: {type(e).__name__} — offline?")
            continue
        if meta:
            info = meta["info"]
            meta_full = meta
            d.resolved_name = n
            d.exists_on_pypi = True
            break

    if not info:
        d.notes.append("No PyPI distribution found under any candidate name. Either it is not "
                       "publicly installable, is distributed privately, or the name differs. "
                       "Do NOT include in a published comparison without a verified artifact.")
        classify(d)
        return d

    d.version = info.get("version")
    d.author = info.get("author") or info.get("maintainer")

    # Release recency decides whether a comparison is *fair*, not just whether it is possible.
    # Benchmarking a package that has had no release in years against a currently-developed engine
    # and publishing it under the vendor's brand misrepresents that vendor's actual product —
    # especially where the live offering has since moved to a hosted platform.
    releases = (meta_full or {}).get("releases", {})
    d.release_count = len(releases) or None
    uploads = [f["upload_time"] for fs in releases.values() for f in fs if f.get("upload_time")]
    if uploads:
        last = max(uploads)
        d.last_release_date = last
        try:
            dt = datetime.strptime(last, "%Y-%m-%dT%H:%M:%S")
            d.days_since_last_release = (datetime.now() - dt).days
        except ValueError:
            pass
    if d.days_since_last_release is not None:
        if d.days_since_last_release > 540:
            d.maintenance_status = "ABANDONED"
            d.notes.append(
                f"No release in {d.days_since_last_release} days. Benchmarking this as the "
                "vendor's current product would misrepresent it — verify whether the live "
                "offering has moved to a hosted platform or a differently-named package before "
                "including it in any published comparison."
            )
        elif d.days_since_last_release > 180:
            d.maintenance_status = "STALE"
            d.notes.append(f"No release in {d.days_since_last_release} days — confirm this is "
                           "still the vendor's current SDK.")
        else:
            d.maintenance_status = "ACTIVE"

    d.requires_python = info.get("requires_python")
    d.license = _license_of(info)
    d.summary = (info.get("summary") or "")[:300]
    d.source_repo = _find_repo(info)
    d.homepage = info.get("home_page")
    reqs = info.get("requires_dist") or []
    d.dependencies = [r.split(";")[0].strip() for r in reqs][:60]
    lowered = " ".join(d.dependencies).lower()
    self_tokens = {candidate.lower(), (d.resolved_name or "").lower()}
    for fw in ("langgraph", "langchain", "crewai", "ray", "llama-index", "autogen"):
        # Exclude self-matches: `llama-index-core` depends on `llama-index-*` siblings, which is
        # not "depends on another framework under test" — it is its own package family.
        if fw in lowered and fw != candidate and not any(fw in t for t in self_tokens):
            d.depends_on_frameworks_under_test.append(fw)

    if do_install and d.resolved_name:
        try_install(d.resolved_name, d)

    detect_telemetry(d)
    classify(d)
    return d


def to_markdown(d: Dossier) -> str:
    def row(k, v):
        return f"| {k} | {v if v not in (None, '', []) else '—'} |"

    lines = [
        f"# Framework dossier — `{d.candidate}`",
        "",
        f"**Track A (execution substrate): {d.track_a_eligible}**  ",
        f"**Track B (orchestration overhead): {d.track_b_eligible}**",
        "",
        "| Field | Value |",
        "| --- | --- |",
        row("Resolved PyPI name", f"`{d.resolved_name}`" if d.resolved_name else None),
        row("Names tried", ", ".join(f"`{n}`" for n in d.tried_names)),
        row("Exists on PyPI", "yes" if d.exists_on_pypi else "**no**"),
        row("Latest version", d.version),
        row("Publisher (PyPI author)", d.author),
        row("Last release", f"{d.last_release_date} "
            f"({d.days_since_last_release}d ago)" if d.last_release_date else None),
        row("Maintenance status", f"**{d.maintenance_status}**"),
        row("Requires Python", d.requires_python),
        row("License", d.license),
        row("License permits publishing results", d.license_permissive),
        row("Source repo", d.source_repo),
        row("Install into clean venv", d.install_ok),
        row("Import check", d.import_ok),
        row("Installed version", d.installed_version),
        row("Execution locality", f"**{d.execution_locality}**"),
        row("Telemetry endpoints", ", ".join(d.telemetry_endpoints)),
        row("Concurrency primitives in own source", ", ".join(d.concurrency_primitives)),
        row("Depends on other frameworks under test", ", ".join(d.depends_on_frameworks_under_test)),
        "",
    ]
    if d.summary:
        lines += [f"> {d.summary}", ""]
    if d.hosted_evidence:
        lines += ["## Vendor-endpoint evidence", "",
                  "Domains in the package's own source that match the vendor's name, after "
                  "excluding LLM-provider endpoints, documentation placeholders and generic "
                  "infrastructure. These warrant a behavioural probe — they do not by themselves "
                  "establish that orchestration is remote.",
                  "", "```"] + d.hosted_evidence + ["```", ""]
    if d.install_error:
        lines += ["## Install error", "", "```", d.install_error, "```", ""]
    if d.dependencies:
        lines += ["## Declared dependencies (first 60)", "",
                  "```", "\n".join(d.dependencies), "```", ""]
    if d.notes:
        lines += ["## Notes", ""] + [f"- {n}" for n in d.notes] + [""]
    lines += ["---", "", "*Generated by `scripts/verify_frameworks.py`. Every field above is read "
              "from the PyPI registry or the installed package's own source. Fields marked "
              "UNVERIFIED were not established and must not be asserted.*"]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates", nargs="*", help="subset of candidates (default: all)")
    ap.add_argument("--install", action="store_true",
                    help="also install each into a disposable venv and introspect its source")
    args = ap.parse_args()

    targets = args.candidates or list(CANDIDATES)
    DOSSIER_DIR.mkdir(parents=True, exist_ok=True)
    all_d: list[Dossier] = []

    for c in targets:
        names = CANDIDATES.get(c, [c])
        print(f"[verify] {c} ... ", end="", flush=True)
        d = build_dossier(c, names, args.install)
        all_d.append(d)
        (DOSSIER_DIR / f"{c}.md").write_text(to_markdown(d))
        (DOSSIER_DIR / f"{c}.json").write_text(json.dumps(asdict(d), indent=2))
        print(f"{d.resolved_name or 'NOT FOUND'} | {d.execution_locality} | "
              f"TrackA={d.track_a_eligible.split(' —')[0]}")

    idx = ["# Framework verification index", "",
           f"Generated for {len(all_d)} candidates. `--install` was "
           f"{'ON' if args.install else 'OFF'}.", "",
           "| Candidate | PyPI | Version | Publisher | Maintenance | License | Locality | Track A |",
           "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for d in all_d:
        idx.append(
            f"| [{d.candidate}]({d.candidate}.md) | {d.resolved_name or '**not found**'} | "
            f"{d.version or '—'} | {(d.author or '—')[:22]} | {d.maintenance_status} | "
            f"{d.license or '—'} | {d.execution_locality} | {d.track_a_eligible.split(' —')[0]} |"
        )
    (DOSSIER_DIR / "INDEX.md").write_text("\n".join(idx) + "\n")
    print(f"\n[verify] wrote {len(all_d)} dossiers -> {DOSSIER_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
