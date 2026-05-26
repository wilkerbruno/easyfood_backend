FROM python:3.11-alpine
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1
CMD ["gunicorn","--bind","0.0.0.0:5000","--workers","2","--timeout","120","wsgi:app"]
