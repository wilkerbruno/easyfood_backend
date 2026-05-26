FROM python:3.11-alpine
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1
HEALTHCHECK --interval=30s --timeout=30s --start-period=60s --retries=5 CMD wget -q http://localhost:5000/health -O - || exit 1
CMD ["gunicorn","--bind","0.0.0.0:5000","--workers","1","--timeout","300","--preload","wsgi:app"]