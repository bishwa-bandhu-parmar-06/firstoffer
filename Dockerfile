# Stage 1: build the React dashboard.
FROM node:20-slim AS dashboard
WORKDIR /build
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY dashboard/ ./
RUN npm run build

# Stage 2: the Python app, which serves the API, the built dashboard, and runs the scheduler.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/
COPY sources.json link_only.json ./
COPY --from=dashboard /build/dist dashboard/dist
EXPOSE 8000
# Render (and most hosts) pass the port to listen on in $PORT.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
