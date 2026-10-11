# Build context = repo's ml/ directory:  docker build -f serve/Dockerfile -t fwr-ml ml/   (or the compose `ml` profile)
# CPU torch by default. GPU box: --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu128 and run with --gpus all.
# (The old pytorch/pytorch:2.5.1 base shipped Python 3.11, which can't install the pinned numpy==2.5.4: the image never built.)
FROM python:3.12-slim
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
# OpenCV (pulled in by ultralytics) needs libGL and glib at import time.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --no-cache-dir --index-url ${TORCH_INDEX} torch==2.9.1 torchvision==0.24.1
COPY serve/requirements.txt /tmp/req.txt
RUN pip install --no-cache-dir -r /tmp/req.txt
COPY yolo/__init__.py yolo/taxonomy.py yolo/infer.py /app/yolo/
COPY ocr/ /app/ocr/
COPY serve/ /app/serve/
ENV PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8000
EXPOSE 8000
# 1 worker: the models are loaded once per process. Never publish this port beyond loopback (no auth).
CMD ["gunicorn", "-w", "1", "--threads", "4", "-t", "120", "-b", "0.0.0.0:8000", "serve.wsgi:app"]
