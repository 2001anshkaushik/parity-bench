<!-- DOCS_HANDOFF_STUB: the document lives on docs-bench -->
# DOCS_HANDOFF — this is a stub, not the document

**The document lives on branch `docs-bench`, at `working/docs/DOCS_HANDOFF.md`.**

```bash
git fetch origin docs-bench
git show origin/docs-bench:working/docs/DOCS_HANDOFF.md
```

* `docs-bench` sha when this stub was written (2026-09-08): `fd9c512` — the live head is whatever `git ls-remote origin docs-bench` reports; that read-back, not this line, is the current sha.
* Any copy of DOCS_HANDOFF prose on this branch (`video-bench`) is **not** the document. The copy that was here was the stale 7-Sep text — it carried a wrong claim in §2.4, a box command that could not run in §5.4 and unlabelled figures — and a fresh session cloning this branch read it as the briefing. It was replaced by this stub on 2026-09-08. `autoland.sh` gate 0b refuses non-stub prose at this path on any branch but `docs-bench`, and refuses a stub on `docs-bench`.
* Merge direction is `video-bench` → `docs-bench` only (`working/docs/AUTOMATION_CONTRACT.md` §2a). Docs work never comes back to this branch, so this stub never needs the document's content.
