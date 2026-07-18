FROM python:3.11-slim

WORKDIR /app

COPY requirements.light.txt .

RUN pip install --no-cache-dir -r requirements.light.txt

COPY . .

EXPOSE 8080

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]