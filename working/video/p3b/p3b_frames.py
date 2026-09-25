"""P3-B frame set (benchmark-only; preregistration.json P3_B). Runs under li:video's Python, which carries the
imageio-ffmpeg binary the LlamaIndex arm uses — byte-identical to the engine's (probe_frame_parity, 2026-08-27) —
and extracts PNG frames with the engine-mirror argv of working/video/li_video/pipeline.py _extract_frames:
fps=1/15, -fps_mode passthrough, -vcodec png. One sub-directory per video; the caller hashes the result.

    python p3b_frames.py --out DIR VIDEO [VIDEO ...]
"""
import argparse
import os
import subprocess

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--interval", type=int, default=15)
ap.add_argument("videos", nargs="+")
a = ap.parse_args()
import imageio_ffmpeg  # noqa: E402
ff = imageio_ffmpeg.get_ffmpeg_exe()
print("ffmpeg", ff, imageio_ffmpeg.__version__)
for i, v in enumerate(a.videos):
    stem = f"v{i:02d}_" + os.path.splitext(os.path.basename(v))[0]
    out = os.path.join(a.out, stem)
    os.makedirs(out)
    subprocess.run([ff, "-nostdin", "-loglevel", "error", "-i", v, "-vf", f"fps=1/{a.interval}",
                    "-f", "image2", "-fps_mode", "passthrough", "-vcodec", "png", os.path.join(out, "f_%06d.png")], check=True)
    print(stem, len(os.listdir(out)))
