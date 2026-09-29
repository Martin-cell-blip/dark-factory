# Pocketful stage 1: a Python standard-library HTTP service. No packages are installed,
# so the image needs no network at run time.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app
COPY pocketful ./pocketful

RUN useradd --system --no-create-home pocketful
USER pocketful

EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8080') + '/health', timeout=2)"

CMD ["python", "-m", "pocketful"]
