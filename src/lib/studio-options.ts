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
    description: "Describe a frame and render a still on your own GPU.",
    icon: ImageIcon,
    connected: true,
  },
  {
    id: "text-to-video",
    label: "Text to Video",
    short: "Video",
    description: "Turn a written scene into a short cinematic clip.",
    icon: Clapperboard,
    connected: false,
  },
  {
    id: "image-to-video",
    label: "Image to Video",
    short: "Animate",
    description: "Bring a reference image to life with guided motion.",
    icon: ImagePlay,
    connected: false,
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

/** What runs each mode. The image model is set by IMAGE_MODEL_ID on the backend; its ID comes from /info. */
export const MODELS: Record<"image" | "video", ModelOption> = {
  image: { id: "local", label: "Local open-weight model", note: "Runs on this machine's GPU through Diffusers" },
  video: { id: "none", label: "Not connected", note: "Video models arrive in a later phase" },
};

/** Output size per tier and aspect ratio; must match IMAGE_SIZES in backend/app/schemas/generation.py. */
export const IMAGE_SIZES: Record<ImageResolution, Record<AspectRatio, [number, number]>> = {
  512: { "1:1": [512, 512], "16:9": [688, 384], "9:16": [384, 688] },
  768: { "1:1": [768, 768], "16:9": [1024, 576], "9:16": [576, 1024] },
  1024: { "1:1": [1024, 1024], "16:9": [1344, 768], "9:16": [768, 1344] },
};

/** What the backend's model offers. Used until /info answers; matches the backend defaults (RealVisXL). */
export type ImageCapabilities = {
  modelId: string | null;
  resolutions: ImageResolution[];
  defaultResolution: ImageResolution;
  stepPresets: number[];
  defaultSteps: number;
};

export const DEFAULT_IMAGE_CAPABILITIES: ImageCapabilities = {
  modelId: null,
  resolutions: [768, 1024],
  defaultResolution: 1024,
  stepPresets: [4, 6, 8],
  defaultSteps: 6,
};

/** Labels for presets in order, smallest first: e.g. 4/6/8 steps → Fast/Balanced/Detailed. */
export function presetLabel(index: number, count: number, labels: [string, string, string]) {
  if (index === 0) return labels[0];
  if (index === count - 1) return labels[2];
  return labels[1];
}

export const SEED_MAX = 4_294_967_295;

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
