FROM python:2
COPY . /app
WORKDIR /app
ENV FLASK_APP jk_flask.py
RUN pip install flask
RUN pip install requests
RUN pip install python-dateutil
RUN pip install enum
CMD flask run --host=0.0.0.0

EXPOSE 5000

