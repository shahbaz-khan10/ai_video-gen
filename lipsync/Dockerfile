# Lip-sync service: MuseTalk 1.5 (Tencent Music, MIT code; models free for any use). Separate container because it
# needs torch 2.0 + the OpenMMLab stack (mmcv/mmdet/mmpose) for face landmarks, which conflict with the backend.
FROM python:3.10-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git libgl1 libglib2.0-0 build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cu118 --extra-index-url https://pypi.org/simple
RUN pip install --no-cache-dir "numpy==1.23.5" "diffusers==0.30.2" "accelerate==0.28.0" "transformers==4.39.2" \
    "huggingface_hub==0.30.2" "opencv-python-headless==4.9.0.80" "soundfile==0.12.1" "librosa==0.11.0" "einops==0.8.1" \
    omegaconf ffmpeg-python imageio[ffmpeg] gdown requests "fastapi>=0.110,<1" "uvicorn>=0.29,<1" openmim
RUN pip install --no-cache-dir mmengine "mmcv==2.0.1" -f https://download.openmmlab.com/mmcv/dist/cu118/torch2.0/index.html \
    && mim install "mmdet==3.1.0" "mmpose==1.1.0"
# mmpose pulls numpy 2.x and an xtcocotools wheel built for it; torch 2.0 needs numpy 1.x ("Numpy is not available",
# "numpy.dtype size changed"). Pin numpy and compile xtcocotools against it (measured fix).
RUN pip install --no-cache-dir --force-reinstall --no-deps numpy==1.23.5     && pip install --no-cache-dir "cython<3.1" setuptools wheel     && pip install --no-cache-dir --no-deps --force-reinstall --no-build-isolation --no-binary xtcocotools "xtcocotools==1.14.3"     && python -c "import numpy, torch, mmpose.datasets; torch.from_numpy(numpy.zeros(1))"
RUN git clone --depth 1 https://github.com/TMElyralab/MuseTalk.git /musetalk
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/musetalk
WORKDIR /musetalk
COPY . /service
EXPOSE 8020
CMD ["uvicorn", "app:app", "--app-dir", "/service", "--host", "0.0.0.0", "--port", "8020"]
