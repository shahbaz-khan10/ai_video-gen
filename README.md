# AI Video Studio

AI image and video generation studio: a Next.js frontend and a FastAPI backend (Phase 4). **Text to Image generates real images with a local open-weight model** (SD-Turbo via Hugging Face Diffusers, on your own GPU). Text to Video and Image to Video are marked "Soon" and only validate settings. There is no auth, database or payment, and project cards are still mock data.

## Stack

Next.js 16 (App Router, Cache Components), TypeScript (strict), Tailwind CSS v4, Motion (`motion/react`), Lucide icons.

## Run

The app has two parts: this Next.js frontend and the FastAPI backend in [`backend/`](backend/README.md).

```powershell
# Terminal 1: backend (http://localhost:8000, docs at /docs)
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000

# Terminal 2: frontend (http://localhost:3000)
npm install                        # first time only
npm run dev
```

First-time backend setup (virtual environment, CUDA PyTorch, Diffusers, and the one-time ~2.6 GB model download) is in [backend/README.md](backend/README.md#setup-windows-powershell).

Checks:

```powershell
npm run lint
npx tsc --noEmit   # run `npx next typegen` first on a fresh clone
npm test           # Vitest: generation state and result UI
npm run build
cd backend; python -m pytest                    # mocked model, no GPU needed
cd backend; python -m pytest -m real_inference  # real model (needs PyTorch + weights)
```

The frontend finds the API through `NEXT_PUBLIC_API_BASE_URL` (see `.env.example`). In development it falls back to `http://localhost:8000`. A production build without it treats the backend as not configured. Without a running backend the studio still works: it shows "Backend offline", and settings are only checked in the browser.

## Routes

| Route | Purpose |
| --- | --- |
| `/` | Landing page |
| `/dashboard` | Studio overview |
| `/create` | Create workspace. Accepts `?mode=`, `?style=` and `?project=` |
| `/projects` | Project library with filters, search and empty state |
| `/projects/[id]` | Project detail with "Open in Create" |
| `/explore` | Visual style library (each style opens Create with it selected) |
| `/settings` | Session-only interface preferences |

The Phase 1 `/studio/*` URLs redirect permanently to the routes above.

## Structure

```
src/
  app/
    page.tsx               landing
    (app)/                 studio routes sharing AppShell (layout, template, loading)
  components/
    layout/                AppShell, AppSidebar, AppHeader, PageContainer, PageHeader
    ui/                    Button, EmptyState, LoadingState, Switch, Tooltip, CopyButton, Poster…
    studio/                ModeSelector, PromptEditor, AspectRatioSelector, StyleSelector,
                           ImageUploader, PreviewPanel, CreateWorkspace…
    projects/              ProjectCard, ProjectThumbnail, ProjectLibrary
    settings/              PreferencesForm
    providers/             PreferencesProvider (in-memory session preferences)
    landing/, motion/, brand/
  lib/                     studio options, mock data, helpers
  lib/api/                 API client (the only place that calls the backend) and status hook
  types/                   shared TypeScript types (studio + API)
backend/                   FastAPI service, see backend/README.md
```

## Notes

- Preferences live in React state only and reset on reload. They feed the Create defaults, the sidebar state and a "Reduce motion" override. The OS reduced-motion setting is always respected.
- Create polls a job every 1.5 s while it is queued or processing and shows the real elapsed time, never a made-up percentage. Finished images load from the backend's file route and download as PNG. Generated images aren't saved to projects yet.
- Uploaded images stay in the browser as object URLs (PNG, JPG or WebP, up to 10 MB). Only the image's type and size are sent to the backend for validation. URLs are revoked when replaced, removed, or unmounted.
