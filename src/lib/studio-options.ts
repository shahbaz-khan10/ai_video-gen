import { Camera, Clapperboard, Film, ImageIcon, ImagePlay, Sparkles, Users, Eye } from "lucide-react";
import type { ImageResolution, VideoResolution } from "@/types/api";
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
    description: "Describe a frame and render a photorealistic raw photograph.",
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
  { id: "photorealistic", label: "Photorealistic", tone: "dusk", note: "Raw 35mm photograph, authentic skin pores, lifelike lighting." },
  { id: "portrait", label: "Portrait Photography", tone: "ember", note: "85mm lens, soft bokeh, studio catchlights, natural facial beauty." },
  { id: "group-photo", label: "Group Photography", tone: "tide", note: "Wide 35mm lens, sharp multi-subject focus, natural spacing." },
  { id: "street", label: "Street Documentary", tone: "noir", note: "35mm candid photojournalism, authentic urban environment." },
  { id: "cinematic", label: "Cinematic", tone: "dusk", note: "Anamorphic framing, motivated light, filmic contrast." },
  { id: "golden-hour", label: "Golden Hour", tone: "ember", note: "Low warm sun, long shadows and rich amber tones." },
  { id: "dreamlike", label: "Dreamlike", tone: "bloom", note: "Soft bloom, pastel haze and floating, weightless atmosphere." },
  { id: "neon-noir", label: "Neon Noir", tone: "noir", note: "Wet streets, magenta practicals, deep shadow." },
  { id: "documentary", label: "Documentary", tone: "tide", note: "Natural light, honest colour, handheld intimacy." },
  { id: "anime", label: "Anime", tone: "aurora", note: "Clean linework, luminous skies and expressive colour." },
];

export const DURATIONS: { id: ClipDuration }[] = [{ id: "4s" }, { id: "6s" }, { id: "8s" }];

export const MODELS: ModelOption[] = [
  { id: "auto", label: "Auto (Realistic Vision V5.1)", note: "Best photorealism, human faces & anatomy" },
  { id: "realistic-vision", label: "Realistic Vision V5.1", note: "Exceptional skin pores, eyes and hands" },
  { id: "sdxl", label: "SDXL Base 1.0", note: "Native 1024x1024 photographic detail" },
  { id: "sd-turbo", label: "SD-Turbo (Fast Draft)", note: "1-4 steps rapid preview" },
];

export const EXAMPLE_PROMPT =
  "A realistic photograph of five people in a modern office with large windows, natural daylight, professional clothes, sharp eye-level 35mm shot.";

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
  high: {
    "1:1": { width: 1024, height: 1024 },
    "16:9": { width: 1344, height: 768 },
    "9:16": { width: 768, height: 1344 },
  },
};

export const IMAGE_RESOLUTIONS: { id: ImageResolution; label: string; hint: string }[] = [
  { id: "standard", label: "Standard (512px)", hint: "Fastest generation, balanced memory usage." },
  { id: "large", label: "Large (768px)", hint: "Crisp detail for portraits and full body photography." },
  { id: "high", label: "Ultra High (1024px)", hint: "Maximum resolution for wide scenes and group shots." },
];

/** Step presets used until /info answers; match the backend's default model (RealVisXL Lightning, 4-8 steps). */
export const DEFAULT_IMAGE_STEPS = [4, 6, 8];

/** Generation modes that actually run on a model today. Image-to-video arrives in a later phase. */
export const LIVE_MODES: GenerationMode[] = ["text-to-image", "text-to-video"];

/**
 * Text-to-video defaults, used until /info answers. They match the backend's Wan2.1 T2V 1.3B limits:
 * at most 81 frames (~5 s at 16 fps), 320p draft or 480p, 10-50 denoising steps.
 */
export const DEFAULT_VIDEO_DURATIONS = [2, 3, 5];
export const DEFAULT_VIDEO_STEPS = [15, 25, 40];

/** Must match VIDEO_SIZES in backend/app/schemas/generation.py. */
export const VIDEO_SIZES: Record<VideoResolution, Record<AspectRatio, { width: number; height: number }>> = {
  standard: {
    "1:1": { width: 416, height: 416 },
    "16:9": { width: 576, height: 320 },
    "9:16": { width: 320, height: 576 },
  },
  large: {
    "1:1": { width: 624, height: 624 },
    "16:9": { width: 832, height: 480 },
    "9:16": { width: 480, height: 832 },
  },
};

export const VIDEO_RESOLUTIONS: { id: VideoResolution; label: string; hint: string }[] = [
  { id: "standard", label: "Draft", hint: "About 320p. Much faster; good for checking motion and framing." },
  { id: "large", label: "Quality", hint: "480p, the model's trained size. Sharper, but takes roughly 3x as long." },
];
