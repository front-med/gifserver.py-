FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# yt-dlpの新リリースが出るとこのADD行のキャッシュが切れ、次のRUNで最新版が入る
# （Renderは--build-argを渡せないため、日時ARGではなくリモートファイル監視方式）
ADD https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/yt_dlp/version.py /tmp/yt-dlp-version.py
RUN pip install --no-cache-dir -U yt-dlp

WORKDIR /app
COPY gifserver.py .

ENV PYTHONUNBUFFERED=1

CMD ["python3", "gifserver.py"]
