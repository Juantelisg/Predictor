FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render inyecta PORT automaticamente
ENV PORT=8900
EXPOSE 8900

CMD uvicorn predictor.app:app --host 0.0.0.0 --port ${PORT:-8900}
