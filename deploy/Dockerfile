FROM python:3.12-alpine

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir -r /tmp/requirements.txt

CMD ["python", "-u", "/app/sync_worker.py"]