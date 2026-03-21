FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY pyproject.toml ./

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "cp -n src/config/local-example-config.json src/config/local-config.json 2>/dev/null; exec uvicorn src.app:app --host 0.0.0.0 --port 8080 --workers 2 --timeout-keep-alive 120"]
