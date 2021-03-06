FROM python:3.7-jessie

ADD . /spider
WORKDIR /spider

RUN pip3 install -r requirements.txt
RUN python3 setup.py install

EXPOSE 7777
CMD python server-test.py