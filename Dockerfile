FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ffmpeg \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY metahuman_platform/requirements.txt /app/metahuman_platform/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/metahuman_platform/requirements.txt

COPY . /app

WORKDIR /app/metahuman_platform
ENV PYTHONPATH=/app:/app/metahuman_platform

EXPOSE 7028

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7028"]
