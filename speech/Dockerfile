# Speech service: Chatterbox TTS (Resemble AI, MIT). Separate from the backend because it pins torch 2.6,
# transformers 5.2 and diffusers 0.29, which conflict with the video stack.
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir chatterbox-tts==0.1.7 "fastapi>=0.115,<1" "uvicorn>=0.30,<1"
ENV HF_HOME=/models PYTHONUNBUFFERED=1
WORKDIR /app
COPY . /app
EXPOSE 8010
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8010"]
