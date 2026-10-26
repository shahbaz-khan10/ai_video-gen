import type { AspectRatio, GenerationMode, PosterTone } from "./studio-options";

/** Mock data for Phase 1. Nothing here was produced by a model. */
export type Project = {
  id: string;
  title: string;
  mode: GenerationMode;
  aspectRatio: AspectRatio;
  style: string;
  tone: PosterTone;
  updated: string;
  duration?: string;
};

export const MOCK_PROJECTS: Project[] = [
  {
    id: "p-01",
    title: "Lighthouse at Blue Hour",
    mode: "text-to-video",
    aspectRatio: "16:9",
    style: "Cinematic",
    tone: "dusk",
    updated: "2 hours ago",
    duration: "0:08",
  },
  {
    id: "p-02",
    title: "Neon Alley Rain",
    mode: "text-to-image",
    aspectRatio: "9:16",
    style: "Neon Noir",
    tone: "noir",
    updated: "Yesterday",
  },
  {
    id: "p-03",
    title: "Aurora Over the Fjord",
    mode: "image-to-video",
    aspectRatio: "16:9",
    style: "Dreamlike",
    tone: "aurora",
    updated: "3 days ago",
    duration: "0:05",
  },
  {
    id: "p-04",
    title: "Desert Caravan, Golden Hour",
    mode: "text-to-video",
    aspectRatio: "1:1",
    style: "Golden Hour",
    tone: "ember",
    updated: "Last week",
    duration: "0:10",
  },
  {
    id: "p-05",
    title: "Tidal Pools Macro",
    mode: "text-to-image",
    aspectRatio: "1:1",
    style: "Documentary",
    tone: "tide",
    updated: "Last week",
  },
  {
    id: "p-06",
    title: "Petals in Zero Gravity",
    mode: "image-to-video",
    aspectRatio: "9:16",
    style: "Dreamlike",
    tone: "bloom",
    updated: "2 weeks ago",
    duration: "0:06",
  },
];

export const MOCK_USER = {
  name: "Guest Creator",
  plan: "Preview workspace",
  initials: "GC",
};
