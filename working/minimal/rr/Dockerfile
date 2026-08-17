# Minimal RocketRide engine image. Same engine, same pin, same entrypoint.
#
# Cut against docker/Dockerfile.rocketride: the arch assertion, `lsof` (installed only so the
# harness can find the listening socket), the pypdf-into-the-embedded-interpreter block (its own
# comment says it is needed ONLY for the legacy pdf_probe node, which the all-stock five-node
# pipeline does not use), and both benchmark probe nodes. See ../REMOVED.md.
#
# Kept: the sha256 pin — a tag is mutable and a hash is not — and the runtime library set, which
# is the measured DT_NEEDED list, not a guess. The engine links LLVM libc++, not libstdc++, and
# its DT_RUNPATH points at the bundled Temurin JRE, so no system Java is installed.
FROM ubuntu:22.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        libc++1 libc++abi1 libunwind8 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ARG ENGINE_URL=https://github.com/rocketride-org/rocketride-server/releases/download/server-v3.3.1/rocketride-server-v3.3.1-linux-x64.tar.gz
ARG ENGINE_SHA256=d8dad45bd084c65443ddb5907965ee1c8424f82fa5dcd5b11476ed66ce0281d8
WORKDIR /opt/rocketride/engine
RUN curl -fL --retry 3 "$ENGINE_URL" -o /tmp/engine.tgz \
    && echo "$ENGINE_SHA256  /tmp/engine.tgz" | sha256sum -c - \
    && tar -xzf /tmp/engine.tgz -C /opt/rocketride/engine \
    && rm /tmp/engine.tgz
ENV ROCKETRIDE_APIKEY=local-dev
EXPOSE 5565
ENTRYPOINT ["./engine", "ai/eaas.py"]
