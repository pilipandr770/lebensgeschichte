FROM python:3.12-slim

# ffmpeg: декодирование аудио для Whisper; pango/harfbuzz: PDF-экспорт через WeasyPrint
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi-dev shared-mime-info fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-optional.txt ./
ARG INSTALL_OPTIONAL=weasyprint
# INSTALL_OPTIONAL=all ставит и faster-whisper (большой образ), =weasyprint только PDF, =none ничего
RUN pip install --no-cache-dir -r requirements.txt \
 && if [ "$INSTALL_OPTIONAL" = "all" ]; then pip install --no-cache-dir -r requirements-optional.txt; \
    elif [ "$INSTALL_OPTIONAL" = "weasyprint" ]; then pip install --no-cache-dir "weasyprint>=62"; fi

COPY . .
ENV DATA_DIR=/data PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8000
# Один воркер и несколько потоков: SQLite не любит много процессов. Для масштабирования см. docs/05-deployment.md
CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--timeout", "300"]
