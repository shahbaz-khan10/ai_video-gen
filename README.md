# AI Video Studio

AI image and video generation studio: a Next.js frontend and a FastAPI backend (Phase 3). No AI models, auth, database or payments are connected: project cards are mock data, and Generate says that generation is not connected yet.

## Stack

Next.js 16 (App Router, Cache Components), TypeScript (strict), Tailwind CSS v4, Motion (`motion/react`), Lucide icons.

## Run

The app has two parts: this Next.js frontend and the FastAPI backend in [`backend/`](backend/README.md).

```powershell
# Terminal 1: backend (http://localhost:8000, docs at /docs)
cd backend
py -3.12 -m venv .venv            # first time only
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt   # first time only
uvicorn app.main:app --reload --port 8000

# Terminal 2: frontend (http://localhost:3000)
npm install                        # first time only
npm run dev
```

Checks:

```powershell
npm run lint
npx tsc --noEmit   # run `npx next typegen` first on a fresh clone
npm run build
cd backend; python -m pytest
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
