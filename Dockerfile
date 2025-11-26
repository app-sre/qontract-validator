##############
# base stage #
##############
FROM registry.access.redhat.com/ubi9/python-312-minimal:9.7-1763382403@sha256:f1ac25dce4f4133304a89bbe668506ccbf08cb38d490cc032652e3f6896eb535 AS base

COPY LICENSE /licenses/LICENSE

#################
# builder stage #
#################
FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.9.13@sha256:f07d1bf7b1fb4b983eed2b31320e25a2a76625bdf83d5ff0208fe105d4d8d2f5 /uv /bin/uv

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
