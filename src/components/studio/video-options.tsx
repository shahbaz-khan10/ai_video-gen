"use client";

import { Film, Timer } from "lucide-react";
import { VIDEO_RESOLUTIONS, VIDEO_SIZES } from "@/lib/studio-options";
import type { VideoResolution } from "@/types/api";
import type { AspectRatio } from "@/types/studio";
import { OptionGroup } from "./option-group";

/** Lengths the backend supports (from /info). Up to 5 s is one clip; longer videos are joined from scene clips. */
export function VideoDurationSelector({
  options,
  fps,
  value,
  onChange,
}: {
  options: number[];
  fps: number;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <OptionGroup
      legend="Clip length"
      hint={`The model renders ${fps} fps clips of at most 5 seconds. Longer videos are split into scenes, each made of several clips, and joined. Time grows with length.`}
      options={options.map((s) => ({ id: String(s) }))}
      value={String(value)}
      onChange={(v) => onChange(Number(v))}
      className={options.length >= 4 ? "grid-cols-4" : options.length === 3 ? "grid-cols-3" : "grid-cols-2"}
      renderOption={(id) => (
        <span className="flex items-center justify-center gap-1.5 py-2 text-xs font-medium">
          <Timer className="size-3.5 opacity-70" aria-hidden />
          {formatSeconds(Number(id))}
        </span>
      )}
    />
  );
}

/** Draft (~320p) or 480p. 720p is not offered: the 1.3B model is unstable there. */
export function VideoSizeSelector({
  value,
  aspectRatio,
  onChange,
  labels,
  hint = "Draft (~320p) is the quickest way to check an idea; Quality is 480p, the model's native size.",
}: {
  value: VideoResolution;
  aspectRatio: AspectRatio;
  onChange: (value: VideoResolution) => void;
  labels?: Record<VideoResolution, string>;
  hint?: string;
}) {
  return (
    <OptionGroup
      legend="Video size"
      hint={hint}
      options={VIDEO_RESOLUTIONS}
      value={value}
      onChange={onChange}
      className="grid-cols-2"
      renderOption={(id) => {
        const option = VIDEO_RESOLUTIONS.find((r) => r.id === id)!;
        const { width, height } = VIDEO_SIZES[id][aspectRatio];
        return (
          <span className="block px-2.5 py-2 text-center" title={option.hint}>
            <span className="flex items-center justify-center gap-1.5 text-xs font-medium">
              <Film className="size-3.5 opacity-70" aria-hidden />
              {labels?.[id] ?? option.label}
            </span>
            <span className="mt-0.5 block font-mono text-[10px] text-fg-subtle">
              {width} × {height}
            </span>
          </span>
        );
      }}
    />
  );
}

function formatSeconds(s: number): string {
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return s % 60 ? `${m}m ${s % 60}s` : `${m}m`;
}
