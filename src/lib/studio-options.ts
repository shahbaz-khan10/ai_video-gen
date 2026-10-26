import type { LucideIcon } from "lucide-react";
import { Clapperboard, ImageIcon, ImagePlay } from "lucide-react";

export type GenerationMode = "text-to-image" | "text-to-video" | "image-to-video";
export type AspectRatio = "16:9" | "9:16" | "1:1";
export type PosterTone = "dusk" | "aurora" | "ember" | "tide" | "noir" | "bloom";

export const MODES: {
  id: GenerationMode;
  label: string;
  short: string;
  description: string;
  icon: LucideIcon;
}[] = [
  {
    id: "text-to-image",
    label: "Text to Image",
    short: "Image",
    description: "Describe a frame and render a high-resolution still.",
    icon: ImageIcon,
  },
  {
    id: "text-to-video",
    label: "Text to Video",
    short: "Video",
    description: "Turn a written scene into a short cinematic clip.",
    icon: Clapperboard,
  },
  {
    id: "image-to-video",
    label: "Image to Video",
    short: "Animate",
    description: "Bring a reference image to life with guided motion.",
    icon: ImagePlay,
  },
];

export const ASPECT_RATIOS: { id: AspectRatio; label: string; hint: string }[] = [
  { id: "16:9", label: "Landscape", hint: "Widescreen, YouTube, presentations" },
  { id: "9:16", label: "Portrait", hint: "Reels, Shorts, Stories" },
  { id: "1:1", label: "Square", hint: "Feeds and thumbnails" },
];

export const VISUAL_STYLES: { id: string; label: string; tone: PosterTone }[] = [
  { id: "cinematic", label: "Cinematic", tone: "dusk" },
  { id: "dreamlike", label: "Dreamlike", tone: "bloom" },
  { id: "neon-noir", label: "Neon Noir", tone: "noir" },
  { id: "documentary", label: "Documentary", tone: "tide" },
  { id: "anime", label: "Anime", tone: "aurora" },
  { id: "golden-hour", label: "Golden Hour", tone: "ember" },
];

export const MODELS: { id: string; label: string; note: string }[] = [
  { id: "auto", label: "Auto (recommended)", note: "Picks the best model for the mode" },
  { id: "studio-motion", label: "Studio Motion · placeholder", note: "Video model slot" },
  { id: "studio-still", label: "Studio Still · placeholder", note: "Image model slot" },
];

export const EXAMPLE_PROMPT =
  "A lone lighthouse on a basalt cliff at blue hour, waves crashing in slow motion, warm beam sweeping through drifting sea mist, anamorphic lens, shallow depth of field, gentle dolly-in.";

export function isMode(value: string | null): value is GenerationMode {
  return MODES.some((m) => m.id === value);
}
