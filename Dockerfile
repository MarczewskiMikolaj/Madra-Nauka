FROM python:3.12-slim

WORKDIR /usr/src/app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY madra ./madra
RUN useradd --create-home madra && mkdir -p /data && chown madra:madra /data
USER madra

EXPOSE 8080

ENV PORT=8080
ENV MADRA_ENV=production
ENV MADRA_DATABASE_PATH=/data/madra.sqlite3

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "2", "app:app"]
