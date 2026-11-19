# Lip-sync service, LatentSync 1.5 (ByteDance, Apache-2.0 code and weights). 8 GB minimum VRAM for inference (README).
# Own container: needs torch 2.5 + insightface/mediapipe, which conflict with MuseTalk's torch 2.0 + OpenMMLab stack.
FROM python:3.10-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git libgl1 libglib2.0-0 build-essential \
    && rm -rf /var/lib/apt/lists/*
# Pinned to the commit this service was written against.
ARG LATENTSYNC_COMMIT=a229c3948406bc2cf6eaf4873e662e70c6a04746
# Shallow fetch of that one commit (a full clone dropped mid-transfer: "RPC failed; curl 56 GnuTLS recv error").
RUN mkdir /latentsync && cd /latentsync && git init -q && git remote add origin https://github.com/bytedance/LatentSync.git \
    && for i in 1 2 3; do git fetch -q --depth 1 origin $LATENTSYNC_COMMIT && break || sleep 10; done \
    && git checkout -q FETCH_HEAD
WORKDIR /latentsync
RUN pip install --no-cache-dir torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121 \
    --extra-index-url https://pypi.org/simple
# gradio is only for their demo app; leave it out.
RUN grep -vE "^(torch|torchvision|gradio)==|^--extra-index-url" requirements.txt > /tmp/req.txt \
    && pip install --no-cache-dir -r /tmp/req.txt "fastapi>=0.110,<1" "uvicorn>=0.29,<1" soundfile
# GFPGAN v1.4 (Apache-2.0) sharpens the redrawn mouth afterwards (restore_mouth.py). basicsr 1.4.2 imports a module
# torchvision removed in 0.17; point it at the current one.
RUN pip install --no-cache-dir gfpgan==1.3.8 basicsr==1.4.2 facexlib==0.3.0 \
    && sed -i "s/torchvision.transforms.functional_tensor import/torchvision.transforms.functional import/" \
       /usr/local/lib/python3.10/site-packages/basicsr/data/degradations.py \
    && python -c "from gfpgan import GFPGANer"
# onnxruntime-gpu (insightface face detector) needs the cuDNN 9 / cuBLAS libraries that the torch wheels ship.
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.10/site-packages/nvidia/cudnn/lib:/usr/local/lib/python3.10/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.10/site-packages/nvidia/cuda_runtime/lib:/usr/local/lib/python3.10/site-packages/nvidia/cufft/lib:/usr/local/lib/python3.10/site-packages/nvidia/curand/lib
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/latentsync HF_HOME=/latentsync/checkpoints/hf
EXPOSE 8020
CMD ["uvicorn", "app:app", "--app-dir", "/service", "--host", "0.0.0.0", "--port", "8020"]
