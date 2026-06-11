FROM python:3.11-slim

WORKDIR /app

# Don't buffer stdout/stderr — logs appear immediately
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create directory for persistent data (SQLite)
RUN mkdir -p /data

CMD ["python", "-m", "bot"]
