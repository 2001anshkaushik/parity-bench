# Minimal LlamaIndex PDF service image. Same model, same threads policy, same offline runtime.
#
# Cut against docker/Dockerfile.llamaindex: the arch assertions (both stages), the harness and
# ladder COPYs, and the split requirements/tail-layer arrangement that exists to protect the
# baked-model build cache across benchmark iterations. See ../REMOVED.md.
#
# Kept: the digest-pinned base, the two-stage build, the baked model and the offline env. A
# runtime model fetch is not a smaller deployment, it is a broken one — and the thread pins are
# load-bearing, since os.cpu_count() reports the HOST's core count inside a --cpus quota and
# unpinned BLAS pools inside forked workers cost most of the concurrency scaling.
FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36 AS builder
ENV PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY working/minimal/li/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ENV HF_HOME=/opt/hf
RUN python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('sentence-transformers/multi-qa-MiniLM-L6-cos-v1', device='cpu')"

FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /opt/hf /opt/hf
ENV HF_HOME=/opt/hf \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    VECLIB_MAXIMUM_THREADS=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY working/minimal/li /app/li
EXPOSE 8801
ENTRYPOINT ["sh", "-c", "exec python -m uvicorn li.service:app --host 0.0.0.0 --port 8801 --workers ${WS1_WORKERS:-32} --loop uvloop --http httptools --no-access-log"]
