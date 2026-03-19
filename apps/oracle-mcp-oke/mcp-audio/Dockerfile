FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
PYTHONUNBUFFERED=1

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
ca-certificates curl && \
rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY tools/ ./tools/
COPY .env ./.env

ENV FASTMCP_PORT=8080 FASTMCP_HOST=0.0.0.0 FASTMCP_APP_NAME=mcp-audio
CMD ["python", "app.py"]
