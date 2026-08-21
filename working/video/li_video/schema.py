"""Wire contract for the video/detect LlamaIndex service.

Isolated so it can move without touching pipeline or HTTP code (the ws1
layering). Everything a gate needs is in the response; everything an identity
check needs is in /health AND repeated per response (the serving pid makes
each response a serving-instance read-back — the probe's census counts
distinct pids across concurrent requests).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProcessVideoResponse(BaseModel):
    # --- workload (gates read these) ------------------------------------
    n_frames: int
    n_detections: int
    detections_per_frame: list[int]
    total_chars: int                      # chars entering the splitter (parity gate input)
    n_chunks: int
    chunk_chars: list[int]                # per-chunk lengths (RR side lacks these; we export them)
    chunk_sha256: list[str]               # per-chunk content hashes (per-arm gates only;
    #                                       cross-arm hash equality stays DECLINED, Phase 1 rule)
    embed_dim: int
    embedding_norms: list[float]          # gate 7: unit-norm within NORM_TOL, both arms
    frame_labels: list[list[str]]         # gate 3: per-frame label multisets (sorted)
    frame_scores: list[list[float]]       # gate 3 triage input (diagnostic only)
    frame_png_sha16: list[str]            # cross-arm frame identity (byte-equal ffmpeg output)

    # --- timings (probe + driver read these) -----------------------------
    stage_s: dict[str, float]             # extract / detect / split / embed
    wall_s: float

    # --- identity (read-backs, not config echoes) ------------------------
    pid: int                              # serving worker process
    detect_impl: str                      # 'rfdetr' — asserted at load, echoed here
    model_names: dict[str, str]           # detector + embedder, from the loaded objects
    torch_num_threads: int                # read INSIDE this process at request time
    versions: dict[str, str | None]       # rfdetr/torch/transformers/... importlib.metadata


class HealthResponse(BaseModel):
    status: str
    pid: int
    warm: bool
    warm_workers: int                     # aggregate marker count (defect #21/#23 pattern)
    declared_workers: int
    detect_impl: str
    model_names: dict[str, str]
    versions: dict[str, str | None]
    torch_num_threads: int
    python_version: str                   # interpreter identity — declared cross-arm, never discovered
    thread_env: dict[str, str | None]     # the six variables, as this process sees them
    split_unit: str                       # 'chars' | 'tokens' — the splitter length semantics
    chunk_size: int
    chunk_overlap: int
    interval_s: int


class ErrorResponse(BaseModel):
    error: str
    pid: int
    detail: str = Field(default='')
