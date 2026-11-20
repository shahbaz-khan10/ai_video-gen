# Storage and GPU rules

## Where data lives

| Data | Size (Nov 2026) | Location | Why |
|---|---|---|---|
| Image/video model weights | 85.8 GB | volume `ai_video-gen_backend-models` (external) | Too big to copy: C: had 120 GB free, no second drive. Linux volume, fast to load. |
| OmniAvatar weights | 19.1 GB | volume `ai_video-gen_omniavatar-models` (external) | same |
| MuseTalk weights | 9.3 GB | volume `ai_video-gen_lipsync-models` (external) | same |
| LatentSync + GFPGAN weights | 6.8 GB | volume `ai_video-gen_latentsync-models` (external) | same |
| Chatterbox weights | 3.2 GB | volume `ai_video-gen_speech-models` (external) | same |
| Recorded voices | <1 MB | `C:\ai-studio-data\voices` (bind mount) | Irreplaceable, small, visible in Windows |
| Generated images/videos/audio | ~0.2 GB | `C:\ai-studio-data\outputs` (bind mount) | Visible in Windows, survives volume loss |

`external: true` means Docker Compose never creates or deletes these volumes, so **`docker compose down -v` cannot
remove the models any more** (it did once and ~60 GB had to be downloaded again). Change the data folder with the
`AVS_DATA_DIR` environment variable (e.g. in `.env`: `AVS_DATA_DIR=E:/ai-studio-data`).

Still: never run `docker volume rm` / `docker volume prune` / `docker system prune --volumes` on this machine.

## Migration that was done (Phase 1, no data lost)

```bash
# 1. copy the small volumes into the Windows folder (read-only sources; the volumes are kept)
mkdir -p /c/ai-studio-data/outputs /c/ai-studio-data/voices
docker run --rm -v ai_video-gen_backend-outputs:/from_out:ro -v ai_video-gen_speech-voices:/from_voices:ro \
  -v C:/ai-studio-data:/to alpine:3.20 sh -c 'cp -a /from_out/. /to/outputs/ && cp -a /from_voices/. /to/voices/'
# verified: 205/205 output files, 2/2 voice files
# 2. switch compose to the bind mounts + external volumes, recreate the containers
docker compose up -d
```

The old `ai_video-gen_backend-outputs` and `ai_video-gen_speech-voices` volumes were left in place as a backup.

## New machine

```bash
for v in backend-models speech-models lipsync-models latentsync-models omniavatar-models; do
  docker volume create ai_video-gen_$v
done
mkdir C:\ai-studio-data\outputs C:\ai-studio-data\voices
docker compose up -d            # backend, latentsync and omniavatar download missing weights on start
```

## Moving the models to a bigger drive later

With a second drive (e.g. `E:`), copy each volume the same way (`docker run --rm -v <volume>:/from:ro -v E:/ai-models/<name>:/to alpine cp -a /from/. /to/`),
point the service at the folder, test, and only then decide about the old volume. Note: loading a 10-20 GB model from a
Windows folder into a Linux container is noticeably slower than from a volume; measure before switching.

## One GPU job at a time

The RTX 3050 has 8 GB of VRAM and the WSL VM 24 GB of RAM. Two model jobs at once fail ("Server out of memory").

* The backend holds `GenerationService._video_lock` for every image, video and talking job, and unloads the image and
  video models and the prompt agent before a talking job.
* `speech` loads Chatterbox only inside `/tts`; `latentsync` / `lipsync` only inside `/lipsync`, in a child process.
  The backend calls both only while holding the lock (`talking_service._run`).
* `omniavatar` is under the Compose profile `experimental` and is not started by `docker compose up`. Run beside the
  backend (manually, outside the lock) it took 17.6 GB RAM and all 8 GB VRAM. It joins the backend's lock in Phase 6.
  To build or try it: `docker compose --profile experimental build omniavatar`.

## Restart behaviour

Every service has `restart: unless-stopped`: after a reboot Docker Desktop brings the stack back once it starts.
(Docker Desktop itself must be set to start with Windows: Settings > General > "Start Docker Desktop when you sign in".)
