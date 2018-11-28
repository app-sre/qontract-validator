FROM centos:7

RUN yum install -y epel-release && yum install -y python-pip && yum clean all

COPY requirements.txt /
RUN pip install -r /requirements.txt

COPY validate.py /validate.py

ENTRYPOINT [ "/validate.py", \
             "--schemas-root", \
             "/data/schemas", \
             "--data-root", \
             "/data/data" ]
