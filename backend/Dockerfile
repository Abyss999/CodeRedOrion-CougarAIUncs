FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod +x /app/entrypoint.sh
EXPOSE 5055
# Runs `flask db upgrade`, then execs gunicorn.
CMD ["/app/entrypoint.sh"]
