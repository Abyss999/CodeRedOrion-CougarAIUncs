# Build context = repo's ml/ directory:  docker build -f serve/Dockerfile -t fwr-ml ml/
# (NOT built on the VPS.) GPU runtime: run with --gpus all on a host with the NVIDIA toolkit.
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime
WORKDIR /app
COPY serve/requirements.txt /tmp/req.txt
RUN pip install --no-cache-dir -r /tmp/req.txt
COPY yolo/__init__.py yolo/taxonomy.py yolo/infer.py /app/yolo/
COPY ocr/ /app/ocr/
COPY serve/ /app/serve/
ENV PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8000
EXPOSE 8000
# 1 worker: models live in GPU memory. Bind to loopback on the host: -p 127.0.0.1:8000:8000
CMD ["gunicorn", "-w", "1", "--threads", "4", "-t", "120", "-b", "0.0.0.0:8000", "serve.wsgi:app"]
