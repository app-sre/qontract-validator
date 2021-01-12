FROM quay.io/centos/centos:7

ENV LC_ALL=en_US.utf8
ENV LANG=en_US.utf8

RUN yum install -y epel-release && \
    yum install -y python36 python36-pip && \
    yum install -y python36-PyYAML && \
    yum clean all && \
    pip3 install --upgrade pip

COPY validator /validator/validator
COPY setup.py /validator

WORKDIR /validator

RUN python3 setup.py install
