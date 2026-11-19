#!/bin/sh
# Fetches OmniAvatar 1.3B and what it builds on into the omniavatar-models volume, once (~19 GB).
cd /omniavatar/pretrained_models || exit 1
[ -s Wan2.1-T2V-1.3B/diffusion_pytorch_model.safetensors ] && [ -s Wan2.1-T2V-1.3B/models_t5_umt5-xxl-enc-bf16.pth ] \
  || huggingface-cli download Wan-AI/Wan2.1-T2V-1.3B --local-dir Wan2.1-T2V-1.3B
[ -s OmniAvatar-1.3B/pytorch_model.pt ] || huggingface-cli download OmniAvatar/OmniAvatar-1.3B --local-dir OmniAvatar-1.3B
[ -s wav2vec2-base-960h/config.json ] || huggingface-cli download facebook/wav2vec2-base-960h --local-dir wav2vec2-base-960h
