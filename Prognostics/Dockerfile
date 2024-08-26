FROM python:3.10.6-slim

RUN mkdir -p /home/app

WORKDIR /home/app

COPY . .

RUN pip3 install -r requirements.txt --progress-bar off

EXPOSE 8568

WORKDIR /home/app/src

CMD ["python3", "deploy_app.py"]
