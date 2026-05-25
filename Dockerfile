# =============================================================
#  EASYFOOD - Dockerfile para EasyPanel
# =============================================================

FROM python:3.11-slim

# Dependências do sistema
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Diretório de trabalho
WORKDIR /app

# Copia requirements primeiro (cache de layers)
COPY requirements.txt .

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn==21.2.0

# Copia o restante do projeto
COPY . .

# Porta que o Flask vai ouvir
EXPOSE 5000

# Variáveis de ambiente padrão
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Comando de inicialização com gunicorn (produção)
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "2", \
     "--threads", "4", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--log-level", "info", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "wsgi:app"]
