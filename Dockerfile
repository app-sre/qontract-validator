##############
# base stage #
##############
FROM registry.access.redhat.com/ubi9/python-312-minimal:9.8-1779375932@sha256:003122481be08ec07bb3a4c702b98bf0d41a60ed6d939fbc250d0245bf8d0c8a AS base

COPY LICENSE /licenses/LICENSE

#################
# builder stage #
#################
FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.16@sha256:440fd6477af86a2f1b38080c539f1672cd22acb1b1a47e321dba5158ab08864d /uv /bin/uv

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
