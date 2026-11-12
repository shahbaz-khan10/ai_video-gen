FROM python:3.12-slim

WORKDIR /app

# Install standard dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install PyTorch with CUDA support (or override via --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cpu)
ARG TORCH_INDEX=https://download.pytorch.org/whl/cu124
COPY backend/requirements-ai.txt ./requirements-ai.txt
RUN pip install --no-cache-dir torch --index-url ${TORCH_INDEX} \
    && pip install --no-cache-dir -r requirements-ai.txt

# Text-to-video extras in their own layer, so changing them does not re-download PyTorch.
COPY backend/requirements-video.txt ./requirements-video.txt
RUN pip install --no-cache-dir -r requirements-video.txt

COPY backend/ ./

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
