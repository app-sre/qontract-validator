##############
# base stage #
##############
FROM registry.access.redhat.com/ubi10/python-314-minimal:10.2-1789951202@sha256:39659b2e2f54adcdbe66315e10edae56e9a7c79ac6e798edebba340535c9c4a3 AS base

COPY LICENSE /licenses/LICENSE

#################
# builder stage #
#################
FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.17@sha256:10787c682e4184e4f290de1171fd4703dc63de99221f10fe1c99002ce7fa9acc /uv /bin/uv

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
