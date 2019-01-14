FROM python:3

RUN pip install flask --proxy http://proxy-wsa.esl.cisco.com:80/
RUN pip install requests  --proxy http://proxy-wsa.esl.cisco.com:80/
RUN pip install python-dateutil  --proxy http://proxy-wsa.esl.cisco.com:80/
#RUN pip install enum  --proxy http://proxy-wsa.esl.cisco.com:80/
CMD flask run --host=0.0.0.0
COPY . /app
WORKDIR /app
ENV FLASK_APP jk_flask.py

EXPOSE 5000

