FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        chromium-driver \
        fonts-liberation \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt certifi
COPY . .

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER=/usr/bin/chromedriver
# Screenshot time stamps are shown to users in India.
ENV TZ=Asia/Kolkata
ENV PORT=8080
ENV HOST=0.0.0.0

CMD ["python", "-m", "app.main"]