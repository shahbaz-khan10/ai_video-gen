# AI Video Studio

Frontend for an AI image and video generation studio. Phase 2 (frontend foundation) is done. No AI models, auth, database or payments are connected: project cards are mock data, and Generate says that generation is not connected yet.

## Stack

Next.js 16 (App Router, Cache Components), TypeScript (strict), Tailwind CSS v4, Motion (`motion/react`), Lucide icons.

## Run

```bash
npm install
npm run dev        # http://localhost:3000
npm run lint
npx tsc --noEmit   # run `npx next typegen` first on a fresh clone
npm run build
```

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
  types/                   shared TypeScript types
```

## Notes

- Preferences live in React state only and reset on reload. They feed the Create defaults, the sidebar state and a "Reduce motion" override. The OS reduced-motion setting is always respected.
- Uploaded images stay in the browser as object URLs (PNG, JPG or WebP, up to 10 MB). URLs are revoked when replaced, removed, or unmounted.
