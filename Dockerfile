FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY bot/requirements.txt bot/requirements.txt

RUN pip install --upgrade pip \
    && pip install -r bot/requirements.txt

COPY . .

CMD ["python", "main.py"]
