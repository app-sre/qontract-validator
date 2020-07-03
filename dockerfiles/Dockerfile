FROM centos:7

ENV LC_ALL=en_US.utf8
ENV LANG=en_US.utf8

RUN yum install -y epel-release && \
    yum install -y python36 python36-pip && \
    yum clean all && \
    pip3 install --upgrade pip && \
    yum clean all

COPY validator /validator/validator
COPY setup.py /validator

WORKDIR /validator

RUN python3 setup.py install
