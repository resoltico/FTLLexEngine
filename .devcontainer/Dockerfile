# Contributor devcontainer for FTLLexEngine.
#
# Why this is not a published runtime image:
# - Contributors need the full Python, shell, native-build, and verification toolchain.
# - Atheris is treated as a contributor-time native fuzzing surface, not a shipped artifact.
# - The repository checkout stays on the host and is bind-mounted into the container.
FROM mcr.microsoft.com/devcontainers/python:1-3.13-bookworm@sha256:0aa711e570b306c02946cdda67587ce8c65978dbb65691341cbcfd4854dfcfff

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

USER root

RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update \
    && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --no-install-recommends \
        build-essential \
        clang-19 \
        libclang-rt-19-dev \
        lsof \
        procps \
        shellcheck \
    && ln -sf /usr/bin/clang-19 /usr/local/bin/clang \
    && ln -sf /usr/bin/clang++-19 /usr/local/bin/clang++ \
    && pip install --no-cache-dir "uv>=0.9.6,<1.0" \
    && python3.13 --version >/dev/null \
    && uv --version >/dev/null \
    && git --version >/dev/null \
    && bash --version >/dev/null \
    && shellcheck --version >/dev/null \
    && clang --version >/dev/null \
    && test -n "$(find "$(clang --print-resource-dir)"/lib/linux -maxdepth 1 -name 'libclang_rt.fuzzer*.a' -print -quit)" \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER vscode
