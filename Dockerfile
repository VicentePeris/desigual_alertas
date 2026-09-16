FROM python:3.11-slim

ENV PYTHONUNBUFFERED True
ENV PORT=8080

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Para Cloud Functions: usa functions-framework
CMD exec functions-framework --target=main --debug --port=$PORT