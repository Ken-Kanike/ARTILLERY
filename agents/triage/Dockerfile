FROM python:3.13-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --target /deps -r requirements.txt

FROM python:3.13-slim
WORKDIR /app
COPY --from=builder /deps /usr/local/lib/python3.13/site-packages/
COPY shared/ ./shared/
COPY agents/__init__.py ./agents/
COPY agents/triage/ ./agents/triage/
ENV PYTHONUNBUFFERED=1 ARTILERY_ENV=production
CMD ["python", "-m", "agents.triage.agent"]
