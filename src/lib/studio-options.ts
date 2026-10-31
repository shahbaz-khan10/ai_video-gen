import { Clapperboard, ImageIcon, ImagePlay } from "lucide-react";
import type { ImageResolution } from "@/types/api";
import type {
  AspectRatio,
  AspectRatioOption,
  ClipDuration,
  GenerationMode,
  ModeOption,
  ModelOption,
  VisualStyle,
} from "@/types/studio";

export const MODES: ModeOption[] = [
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

export const ASPECT_RATIOS: AspectRatioOption[] = [
  { id: "16:9", label: "Landscape", hint: "Widescreen, YouTube, presentations" },
  { id: "9:16", label: "Portrait", hint: "Reels, Shorts, Stories" },
  { id: "1:1", label: "Square", hint: "Feeds and thumbnails" },
];

export const VISUAL_STYLES: VisualStyle[] = [
  { id: "cinematic", label: "Cinematic", tone: "dusk", note: "Anamorphic framing, motivated light, filmic contrast." },
  { id: "dreamlike", label: "Dreamlike", tone: "bloom", note: "Soft bloom, pastel haze and floating, weightless motion." },
  { id: "neon-noir", label: "Neon Noir", tone: "noir", note: "Wet streets, magenta practicals, deep shadow." },
  { id: "documentary", label: "Documentary", tone: "tide", note: "Natural light, honest colour, handheld intimacy." },
  { id: "anime", label: "Anime", tone: "aurora", note: "Clean linework, luminous skies and expressive colour." },
  { id: "golden-hour", label: "Golden Hour", tone: "ember", note: "Low warm sun, long shadows and rich amber tones." },
];

export const DURATIONS: { id: ClipDuration }[] = [{ id: "4s" }, { id: "6s" }, { id: "8s" }];

export const MODELS: ModelOption[] = [
  { id: "auto", label: "Auto (recommended)", note: "Picks the best model for the mode" },
  { id: "studio-motion", label: "Studio Motion · placeholder", note: "Video model slot" },
  { id: "studio-still", label: "Studio Still · placeholder", note: "Image model slot" },
];

export const EXAMPLE_PROMPT =
  "A lone lighthouse on a basalt cliff at blue hour, waves crashing in slow motion, warm beam sweeping through drifting sea mist, anamorphic lens, shallow depth of field, gentle dolly-in.";

export function isMode(value: string | null | undefined): value is GenerationMode {
  return MODES.some((m) => m.id === value);
}

export function getMode(id: GenerationMode) {
  return MODES.find((m) => m.id === id)!;
}

export function getStyle(id: string) {
  return VISUAL_STYLES.find((s) => s.id === id) ?? VISUAL_STYLES[0];
}

export function isVideoMode(mode: GenerationMode) {
  return mode !== "text-to-image";
}

/** Mirrors backend IMAGE_SIZES: the server, not the client, decides exact pixels. */
export const IMAGE_SIZES: Record<ImageResolution, Record<AspectRatio, { width: number; height: number }>> = {
  standard: {
    "1:1": { width: 512, height: 512 },
    "16:9": { width: 680, height: 384 },
    "9:16": { width: 384, height: 680 },
  },
  large: {
    "1:1": { width: 768, height: 768 },
    "16:9": { width: 1024, height: 576 },
    "9:16": { width: 576, height: 1024 },
  },
};

export const IMAGE_RESOLUTIONS: { id: ImageResolution; label: string; hint: string }[] = [
  { id: "standard", label: "Standard", hint: "Native size for SD-Turbo. Fastest and most reliable." },
  { id: "large", label: "Large", hint: "More pixels, slower, and needs more memory. Composition can repeat." },
];

export const IMAGE_STEPS: { id: "1" | "2" | "4"; label: string }[] = [
  { id: "1", label: "Fast" },
  { id: "2", label: "Balanced" },
  { id: "4", label: "Detailed" },
];

/** Generation modes that actually run on a model today. */
export const LIVE_MODES: GenerationMode[] = ["text-to-image"];
