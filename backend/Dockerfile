FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY backend/ backend/
COPY optimizer.py cart_create.py ./
COPY art/ art/

CMD ["python", "backend/api.py"]
