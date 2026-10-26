import type { Project } from "@/types/studio";

/** Mock data. Nothing here was produced by a model. */
export const MOCK_PROJECTS: Project[] = [
  {
    id: "lighthouse-blue-hour",
    title: "Lighthouse at Blue Hour",
    mode: "text-to-video",
    aspectRatio: "16:9",
    styleId: "cinematic",
    tone: "dusk",
    prompt:
      "A lone lighthouse on a basalt cliff at blue hour, waves crashing in slow motion, warm beam sweeping through drifting sea mist, anamorphic lens, gentle dolly-in.",
    updated: "2 hours ago",
    created: "Oct 24, 2026",
    duration: "8s",
  },
  {
    id: "neon-alley-rain",
    title: "Neon Alley Rain",
    mode: "text-to-image",
    aspectRatio: "9:16",
    styleId: "neon-noir",
    tone: "noir",
    prompt:
      "A narrow alley in heavy rain at night, magenta and cyan neon signs reflecting in puddles, a figure with a clear umbrella, 35mm, high contrast.",
    updated: "Yesterday",
    created: "Oct 23, 2026",
  },
  {
    id: "aurora-fjord",
    title: "Aurora Over the Fjord",
    mode: "image-to-video",
    aspectRatio: "16:9",
    styleId: "dreamlike",
    tone: "aurora",
    prompt: "Slow ripples of green aurora drift across the sky while still water mirrors the light; subtle push-in.",
    updated: "3 days ago",
    created: "Oct 21, 2026",
    duration: "4s",
  },
  {
    id: "desert-caravan",
    title: "Desert Caravan, Golden Hour",
    mode: "text-to-video",
    aspectRatio: "1:1",
    styleId: "golden-hour",
    tone: "ember",
    prompt:
      "A camel caravan crossing tall dunes at golden hour, long shadows, heat shimmer, drone shot slowly tracking left.",
    updated: "Last week",
    created: "Oct 17, 2026",
    duration: "8s",
  },
  {
    id: "tidal-pools",
    title: "Tidal Pools Macro",
    mode: "text-to-image",
    aspectRatio: "1:1",
    styleId: "documentary",
    tone: "tide",
    prompt: "Macro photograph of a tidal pool, anemones and tiny shells under clear water, soft overcast light, natural colour.",
    updated: "Last week",
    created: "Oct 15, 2026",
  },
  {
    id: "petals-zero-gravity",
    title: "Petals in Zero Gravity",
    mode: "image-to-video",
    aspectRatio: "9:16",
    styleId: "dreamlike",
    tone: "bloom",
    prompt: "Pink petals float upward and slowly rotate in weightless air, soft bloom, pastel haze, gentle camera sway.",
    updated: "2 weeks ago",
    created: "Oct 10, 2026",
    duration: "6s",
  },
];

export function getProject(id: string) {
  return MOCK_PROJECTS.find((p) => p.id === id);
}

export const MOCK_USER = {
  name: "Guest Creator",
  plan: "Preview workspace",
  initials: "GC",
};
