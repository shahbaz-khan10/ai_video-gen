import type { LucideIcon } from "lucide-react";

export type GenerationMode = "text-to-image" | "text-to-video" | "image-to-video";
export type AspectRatio = "16:9" | "9:16" | "1:1";
export type ClipDuration = "4s" | "6s" | "8s";
export type PosterTone = "dusk" | "aurora" | "ember" | "tide" | "noir" | "bloom";

export type ModeOption = {
  id: GenerationMode;
  label: string;
  short: string;
  description: string;
  icon: LucideIcon;
};

export type AspectRatioOption = { id: AspectRatio; label: string; hint: string };
export type VisualStyle = { id: string; label: string; tone: PosterTone; note: string };
export type ModelOption = { id: string; label: string; note: string };

/** A saved project. Only mock projects exist so far; nothing was produced by a model. */
export type Project = {
  id: string;
  title: string;
  mode: GenerationMode;
  aspectRatio: AspectRatio;
  styleId: string;
  tone: PosterTone;
  prompt: string;
  updated: string;
  created: string;
  duration?: ClipDuration;
};

/** Initial values the Create workspace starts from. */
export type CreateDraft = {
  mode: GenerationMode;
  prompt: string;
  aspectRatio: AspectRatio;
  styleId: string;
  duration: ClipDuration;
};

/** In-memory interface preferences. They reset on reload by design. */
export type Preferences = {
  defaultMode: GenerationMode;
  defaultAspectRatio: AspectRatio;
  defaultStyleId: string;
  reduceMotion: boolean;
  startSidebarCollapsed: boolean;
};
