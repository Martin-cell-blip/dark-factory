# Pocketful stage 4: a Python standard-library HTTP service that also serves the browser
# app from pocketful/web. No packages are installed, so nothing is fetched at run time.
FROM python:3.12-slim

# MALLOC_ARENA_MAX keeps glibc from growing one heap per request thread, so memory
# freed after large requests is reused instead of piling up.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MALLOC_ARENA_MAX=2 \
    PORT=8080

WORKDIR /app
COPY pocketful ./pocketful

RUN useradd --system --no-create-home pocketful
USER pocketful

EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8080') + '/health', timeout=2)"

CMD ["python", "-m", "pocketful"]
