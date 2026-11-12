"use client";

import { Film, Timer } from "lucide-react";
import { VIDEO_RESOLUTIONS, VIDEO_SIZES } from "@/lib/studio-options";
import type { VideoResolution } from "@/types/api";
import type { AspectRatio } from "@/types/studio";
import { OptionGroup } from "./option-group";

/** Clip lengths the video model supports (from /info). Wan 1.3B tops out at 81 frames, about 5 s. */
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
      hint={`The model renders at ${fps} fps and at most about 5 seconds. Longer clips take proportionally longer.`}
      options={options.map((s) => ({ id: String(s) }))}
      value={String(value)}
      onChange={(v) => onChange(Number(v))}
      className={options.length >= 3 ? "grid-cols-3" : "grid-cols-2"}
      renderOption={(id) => (
        <span className="flex items-center justify-center gap-1.5 py-2 text-xs font-medium">
          <Timer className="size-3.5 opacity-70" aria-hidden />
          {id}s
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
}: {
  value: VideoResolution;
  aspectRatio: AspectRatio;
  onChange: (value: VideoResolution) => void;
}) {
  return (
    <OptionGroup
      legend="Video size"
      hint="Draft is the quickest way to check an idea; 480p is the model's native size."
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
              {option.label}
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
