# base
FROM registry.access.redhat.com/ubi9/ubi-minimal:9.5 AS base

ENV HOME=/validator \
    USER=app \
    PATH=/validator/.local/bin:$PATH

USER 0

COPY LICENSE /licenses/LICENSE

RUN microdnf install -y python3.11 python3.11-pip && \
    update-alternatives --install /usr/bin/python3 python /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/pip3 pip /usr/bin/pip3.11 1

RUN useradd -u 1001 -g root -d ${HOME} -m -s /sbin/nologin -c "Default Application User" ${USER}

WORKDIR $HOME

# test
FROM base AS test
USER app
ENV TOX_PARALLEL_NO_SPINNER=1
RUN python3 -m pip install tox
COPY --chown=$USER . $HOME
CMD ["tox"]

# prod
FROM base AS prod
USER app
COPY --chown=$USER validator $HOME/validator
COPY --chown=$USER setup.py $HOME
RUN pwd && ls -al && env && python3 -m pip install -e .
