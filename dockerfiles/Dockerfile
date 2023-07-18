FROM registry.access.redhat.com/ubi9/ubi-minimal:9.2

ENV LC_ALL=en_US.utf8
ENV LANG=en_US.utf8

RUN microdnf upgrade -y && \
    microdnf install -y \
        python3.11 glibc-langpack-en && \
    microdnf clean all && \
    update-alternatives --install /usr/bin/python3 python /usr/bin/python3.11 1 && \
    python3 -m ensurepip

RUN python3 -m pip install --no-cache-dir --upgrade pip setuptools

WORKDIR /validator
COPY validator /validator/validator
COPY setup.py /validator

RUN python3 -m pip install --no-cache-dir --upgrade pip setuptools && \
    python3 -m pip install -e .
