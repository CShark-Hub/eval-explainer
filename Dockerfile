# Eval explainer: stdlib-only Python, no dependencies to install.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY serve.py index.html ./
# Result files come in as a read-only volume (see compose.yaml); the image has none.
RUN mkdir -p /data/results /data/cases
USER nobody
EXPOSE 8077
CMD ["python3", "serve.py", "--results", "/data/results", "--cases", "/data/cases", "--host", "0.0.0.0", "--port", "8077"]
