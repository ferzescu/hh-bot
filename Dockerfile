FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2t64 libxshmfence1 libxfixes3 \
    libx11-xcb1 libxcb-dri3-0 libxcb1 libx11-6 libxext6 \
    fonts-unifont fonts-liberation fonts-noto-color-emoji && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium

COPY bot/ bot/

VOLUME /app/storage

CMD ["python", "-m", "bot.main"]
