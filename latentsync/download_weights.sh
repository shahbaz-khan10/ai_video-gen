#!/bin/sh
# Fetches LatentSync 1.5 weights into the latentsync-models volume if they are missing (~5.2 GB once).
cd /latentsync || exit 1
[ -s checkpoints/latentsync_unet.pt ] && [ -s checkpoints/whisper/tiny.pt ] \
  || huggingface-cli download ByteDance/LatentSync-1.5 whisper/tiny.pt latentsync_unet.pt --local-dir checkpoints
# The VAE is loaded by repo id from HF_HOME (checkpoints/hf).
huggingface-cli download stabilityai/sd-vae-ft-mse config.json diffusion_pytorch_model.safetensors > /dev/null
