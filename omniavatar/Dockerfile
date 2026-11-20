# OmniAvatar (Apache-2.0): audio-driven talking video on Wan2.1-T2V-1.3B. The whole clip is generated from the audio
# and a reference image, so it needs no face detector and can animate animals and cartoon characters, unlike the
# mouth-inpainting lip-sync services (MuseTalk, LatentSync) that only find human faces.
FROM python:3.10-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git libgl1 libglib2.0-0 build-essential \
    && rm -rf /var/lib/apt/lists/*
ARG OMNIAVATAR_COMMIT=1536bf31abaec74364fb7d5883470d5b23ffa7f8
RUN mkdir /omniavatar && cd /omniavatar && git init -q && git remote add origin https://github.com/Omni-Avatar/OmniAvatar.git \
    && for i in 1 2 3; do git fetch -q --depth 1 origin $OMNIAVATAR_COMMIT && break || sleep 10; done \
    && git checkout -q FETCH_HEAD
WORKDIR /omniavatar
# torch built for CUDA 12.1 (the newest PyPI wheels need a newer driver than this machine's 12.6).
RUN pip install --no-cache-dir torch==2.4.1 torchvision==0.19.1 torchaudio==2.4.1 \
    --index-url https://download.pytorch.org/whl/cu121 --extra-index-url https://pypi.org/simple
# xfuser pulls the newest diffusers, which needs peft>=0.17 and a newer torch ("infer_schema ... unsupported type");
# diffusers 0.31 (xfuser 0.4.1's era) works with this torch and OmniAvatar's own peft 0.15.1 (measured).
# torch is pinned here again: without it pip backtracked through 7 torch wheels (2.10 down to 2.6, ~900 MB each,
# ~8 min) before settling back on 2.4.1, and a rebuild was stopped for lack of memory midway.
RUN pip install --no-cache-dir -r requirements.txt "diffusers==0.31.0" "huggingface_hub[cli]<1" \
    "torch==2.4.1" "torchvision==0.19.1" "torchaudio==2.4.1" \
    --extra-index-url https://download.pytorch.org/whl/cu121 \
    "fastapi>=0.110,<1" "uvicorn>=0.29,<1" \
    && python -c "import torch, transformers, peft, librosa, diffusers.models.autoencoders.autoencoder_kl; print(torch.__version__)"
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/omniavatar HF_HUB_DISABLE_PROGRESS_BARS=1
EXPOSE 8030
CMD ["sh", "-c", "sh /service/download_weights.sh; exec uvicorn app:app --app-dir /service --host 0.0.0.0 --port 8030"]
