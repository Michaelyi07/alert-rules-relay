# Build context is the REPOSITORY ROOT (docker-compose.yml build: .).
# app.py uses a package-relative import, so the module path must be relay.app.
FROM python:3.11-slim
WORKDIR /app
COPY relay/requirements.txt ./relay/requirements.txt
RUN pip install --no-cache-dir -r relay/requirements.txt
COPY relay/ ./relay/
EXPOSE 8080
CMD ["uvicorn", "relay.app:app", "--host", "0.0.0.0", "--port", "8080"]
