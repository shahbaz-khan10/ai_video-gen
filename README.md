# AI Video Studio

AI image and video generation studio: a Next.js frontend and a FastAPI backend (Phase 5). **Text to Image** (RealVisXL V5.0 Lightning) and **Text to Video** (Wan2.1 T2V 1.3B with the FastWan2.1 3-step transformer, both Apache-2.0; 2-5 s clips or 15-120 s videos joined from planned scenes) run on local open-weight models on your own GPU; no paid or remote API is used. Image to Video is not implemented yet. There is no auth, database or payment, and project cards are mock data.

## Stack

Next.js 16 (App Router, Cache Components), TypeScript (strict), Tailwind CSS v4, Motion (`motion/react`), Lucide icons.

## Run

The app has two parts: this Next.js frontend and the FastAPI backend in [`backend/`](backend/README.md).

**Docker (recommended on Windows; Smart App Control blocks PyTorch outside it):**

```powershell
docker compose up -d --build   # frontend http://localhost:3001, backend http://localhost:8003 (docs at /docs)
```

The models (RealVisXL ~6.9 GB, Wan2.1 ~29 GB, FastWan transformer ~6 GB) live in the `backend-models` volume; first-time download and the 24 GB Docker RAM setting are in [backend/README.md](backend/README.md#text-to-video-phase-5).

**Without Docker:**

```powershell
# Terminal 1: backend (http://localhost:8000, docs at /docs)
cd backend
py -3.12 -m venv .venv            # first time only
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt   # first time only
python -m uvicorn app.main:app --reload --port 8000

# Terminal 2: frontend (http://localhost:3000)
npm install                        # first time only
npm run dev
```

Checks:

```powershell
npm run lint
npx tsc --noEmit   # run `npx next typegen` first on a fresh clone
npm test           # job state logic (Node test runner)
npm run build
cd backend; python -m pytest   # mocked models; real inference: AVS_RUN_REAL_INFERENCE=1
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
- Uploaded images stay in the browser as object URLs (PNG, JPG or WebP, up to 10 MB). Only the image's type and size are sent to the backend for validation. URLs are revoked when replaced, removed, or unmounted.
