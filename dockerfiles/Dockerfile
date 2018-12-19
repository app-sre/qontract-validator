FROM centos:7

RUN yum install -y epel-release && \
    yum install -y python2-pip && \
    pip install --upgrade pip && \
    yum clean all

COPY validator /validator/validator
COPY setup.py /validator

WORKDIR /validator

RUN python setup.py install
