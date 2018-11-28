FROM centos:7

ENV APP_ROOT /validator

RUN yum install -y epel-release && yum install -y python-pip && yum clean all

COPY requirements.txt /
RUN pip install -r /requirements.txt

RUN mkdir ${APP_ROOT}}
COPY validate.py ${APP_ROOT}/validate.py

WORKDIR ${APP_ROOT}
ENTRYPOINT [ "./validate.py" ]
