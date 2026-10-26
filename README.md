# AI Video Studio

Phase 1: the frontend UI/UX for an AI image and video generation studio. No AI models, auth, database or payments are connected yet. Project cards are mock data, and the Generate button says that generation is not connected.

## Stack

Next.js 16 (App Router), TypeScript, Tailwind CSS v4, Motion (`motion/react`), Lucide icons.

## Run

```bash
npm install
npm run dev        # http://localhost:3000
npm run lint
npm run build
```

## Routes

| Route | Purpose |
| --- | --- |
| `/` | Landing page |
| `/studio` | Dashboard overview |
| `/studio/create` | Create workspace (`?mode=text-to-image \| text-to-video \| image-to-video`) |
| `/studio/projects` | Project library with filters, search and empty state |
| `/studio/explore` | Visual style library |
| `/studio/settings` | Settings placeholders |

## Structure

```
src/
  app/                 routes, root layout, design tokens (globals.css)
  components/
    ui/                button, tooltip, empty state, CSS-generated poster artwork
    motion/            MotionConfig provider (respects reduced motion), scroll reveal
    landing/           header, hero, features, workflow, footer
    studio/            shell, collapsible sidebar, project cards, page headers
    create/            mode selector, prompt editor, uploader, settings, preview
  lib/                 studio options, mock data, helpers
```
