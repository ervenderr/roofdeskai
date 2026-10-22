# Railway build: API + demo page. Local dev uses api/Dockerfile via docker-compose.
FROM python:3.12-slim
WORKDIR /srv
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api/app app
COPY prompts prompts
COPY clients clients
COPY site site
COPY db db
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
