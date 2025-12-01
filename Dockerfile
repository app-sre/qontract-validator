##############
# base stage #
##############
FROM registry.access.redhat.com/ubi9/python-312-minimal:9.7-1764607194@sha256:ef11e00a2e2ef2cf47e8a047b00f9fe6b61327f99839c073b5a42c01d7eea373 AS base

COPY LICENSE /licenses/LICENSE

#################
# builder stage #
#################
FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.9.14@sha256:fef8e5fb8809f4b57069e919ffcd1529c92b432a2c8d8ad1768087b0b018d840 /uv /bin/uv

ENV \
    # use venv from ubi image
    UV_PROJECT_ENVIRONMENT="/opt/app-root" \
    # compile bytecode for faster startup
    UV_COMPILE_BYTECODE="true" \
    # disable uv cache. it doesn't make sense in a container
    UV_NO_CACHE=true

COPY pyproject.toml uv.lock ./
# Test lock file is up to date
RUN uv lock --locked
# Install the project dependencies
RUN uv sync --frozen --no-install-project --no-group dev

COPY README.md ./
COPY validator ./validator
RUN uv sync --frozen --no-group dev

##############
# test stage #
##############
FROM builder AS test
USER 0
RUN microdnf -y install make && microdnf -y clean all
USER 1001
COPY Makefile ./
RUN uv sync --frozen
RUN make _test

##############
# prod stage #
##############
FROM base AS prod
COPY --from=builder /opt/app-root /opt/app-root
