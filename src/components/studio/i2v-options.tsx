"use client";

import { Film, Gauge, Sparkles, Timer, Video, Wind } from "lucide-react";
import { I2V_CAMERAS, I2V_MOTIONS, I2V_QUALITIES, estimateI2VSeconds } from "@/lib/studio-options";
import type { I2VCamera, I2VMotion, I2VQuality, T2VQuality, VideoResolution } from "@/types/api";
import { OptionGroup } from "./option-group";

/** Draft or Quality sampling. The estimates are measured times on the RTX 3050 (docs/phase_k). */
export function I2VQualitySelector({
  value,
  onChange,
  seconds,
  resolution,
}: {
  value: I2VQuality;
  onChange: (value: I2VQuality) => void;
  seconds: number;
  resolution: VideoResolution;
}) {
  return (
    <OptionGroup
      legend="Mode"
      hint="Draft samples in 3 distilled steps and kept faces and details closest to the photo in our tests. Quality uses 20 steps with guidance: bigger, more prompt-following motion, but faces and details drift more and it is about 4x slower. Ken Burns uses no AI model: a slow zoom or pan over the photo (pick it under Camera), ready in about a second; the people in the photo do not move."
      options={I2V_QUALITIES}
      value={value}
      onChange={onChange}
      className="grid-cols-3"
      renderOption={(id) => {
        const option = I2V_QUALITIES.find((q) => q.id === id)!;
        const Icon = id === "draft" ? Gauge : id === "quality" ? Sparkles : Film;
        return (
          <span className="block px-2.5 py-2 text-center">
            <span className="flex items-center justify-center gap-1.5 text-xs font-medium">
              <Icon className="size-3.5 opacity-70" aria-hidden />
              {option.label}
            </span>
            <span className="mt-0.5 block text-[10px] text-fg-subtle">≈ {formatEstimate(estimateI2VSeconds(id, resolution, seconds))}</span>
          </span>
        );
      }}
    />
  );
}

const T2V_QUALITIES: { id: T2VQuality; label: string; note: string }[] = [
  { id: "fast", label: "Fast · Wan 2.1", note: "≈ 1–2 min for 5 s" },
  { id: "high", label: "High · Wan 2.2", note: "≈ 10 min for 2 s (480p)" },
];

/** Text-to-video model. Times measured on the RTX 3050 8 GB (scripts/benchmark_wan22.py). */
export function T2VQualitySelector({
  value,
  onChange,
  highAvailable,
  highDetail,
}: {
  value: T2VQuality;
  onChange: (value: T2VQuality) => void;
  highAvailable: boolean;
  highDetail?: string;
}) {
  return (
    <OptionGroup
      legend="Model"
      hint={
        "Fast (FastWan 2.1, 3 steps) is sharp and quick but motion is often small. High (Wan 2.2 5B, 24 fps) gave " +
        "more natural motion and camera movement in our test, with a softer picture, and is many times slower on " +
        "an 8 GB GPU. High makes single clips of up to 5 s." +
        (highAvailable ? "" : ` Not available on this server: ${highDetail || "model not downloaded."}`)
      }
      options={T2V_QUALITIES}
      value={value}
      onChange={(id) => (id === "high" && !highAvailable ? undefined : onChange(id))}
      className="grid-cols-2"
      renderOption={(id) => {
        const option = T2V_QUALITIES.find((q) => q.id === id)!;
        const disabled = id === "high" && !highAvailable;
        return (
          <span className={`block px-2.5 py-2 text-center ${disabled ? "opacity-40" : ""}`}>
            <span className="flex items-center justify-center gap-1.5 text-xs font-medium">
              {id === "fast" ? <Gauge className="size-3.5 opacity-70" aria-hidden /> : <Sparkles className="size-3.5 opacity-70" aria-hidden />}
              {option.label}
            </span>
            <span className="mt-0.5 block text-[10px] text-fg-subtle">{disabled ? "Not downloaded" : option.note}</span>
          </span>
        );
      }}
    />
  );
}

export function I2VDurationSelector({
  options,
  value,
  onChange,
}: {
  options: number[];
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <OptionGroup
      legend="Clip length"
      hint="One clip of at most 5 seconds (81 frames at 16 fps), the model's limit. Every frame after the first is generated."
      options={options.map((s) => ({ id: String(s) }))}
      value={String(value)}
      onChange={(v) => onChange(Number(v))}
      className="grid-cols-3"
      renderOption={(id) => (
        <span className="flex items-center justify-center gap-1.5 py-2 text-xs font-medium">
          <Timer className="size-3.5 opacity-70" aria-hidden />
          {id}s
        </span>
      )}
    />
  );
}

export function I2VMotionSelector({ value, onChange }: { value: I2VMotion; onChange: (value: I2VMotion) => void }) {
  return (
    <OptionGroup
      legend="Motion strength"
      hint="Added to your motion prompt as words (the model has no numeric motion control). Subtle keeps the picture closest to the photo."
      options={I2V_MOTIONS}
      value={value}
      onChange={onChange}
      className="grid-cols-3"
      renderOption={(id) => (
        <span className="flex items-center justify-center gap-1.5 py-2 text-xs font-medium">
          <Wind className="size-3.5 opacity-70" aria-hidden />
          {I2V_MOTIONS.find((m) => m.id === id)!.label}
        </span>
      )}
    />
  );
}

export function I2VCameraSelector({ value, onChange }: { value: I2VCamera; onChange: (value: I2VCamera) => void }) {
  return (
    <OptionGroup
      legend="Camera"
      hint="None adds no camera words, so the camera only moves if your prompt asks for it. Static asks the model to keep the frame still."
      options={I2V_CAMERAS}
      value={value}
      onChange={onChange}
      className="grid-cols-4"
      renderOption={(id) => (
        <span className="flex items-center justify-center gap-1 py-2 text-[11px] font-medium">
          <Video className="size-3 opacity-70" aria-hidden />
          {I2V_CAMERAS.find((c) => c.id === id)!.label}
        </span>
      )}
    />
  );
}

export function formatEstimate(seconds: number): string {
  if (seconds < 90) return `${Math.round(seconds / 5) * 5}s`;
  return `${Math.round(seconds / 30) / 2} min`;
}
