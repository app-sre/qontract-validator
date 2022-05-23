FROM registry.access.redhat.com/ubi8/ubi-minimal:8.6

ENV LC_ALL=en_US.utf8
ENV LANG=en_US.utf8

RUN microdnf install \
        python3.9 && \
    microdnf clean all

RUN python3 -m pip install --no-cache-dir --upgrade pip setuptools

WORKDIR /validator
COPY validator /validator/validator
COPY setup.py /validator

RUN python3 -m pip install --no-cache-dir --upgrade pip setuptools && \
    python3 -m pip install -e .
