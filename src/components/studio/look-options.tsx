"use client";

import { Switch } from "@/components/ui/switch";
import { VIDEO_LOOKS } from "@/lib/studio-options";
import type { VideoLook } from "@/types/api";
import { OptionGroup } from "./option-group";

/** ffmpeg colour/grain presets, applied on the CPU after the video is generated (~0.5 s for 5 s). */
export function LookSelector({ value, onChange }: { value: VideoLook; onChange: (value: VideoLook) => void }) {
  const current = VIDEO_LOOKS.find((l) => l.id === value) ?? VIDEO_LOOKS[0];
  return (
    <div className="flex flex-col gap-2">
      <OptionGroup
        legend="Look"
        hint="A colour and grain finish added after generation with ffmpeg. It takes about half a second and does not use the GPU."
        options={VIDEO_LOOKS}
        value={value}
        onChange={onChange}
        className="grid-cols-3 sm:grid-cols-5"
        renderOption={(id) => (
          <span className="block px-2 py-2 text-center text-xs font-medium">{VIDEO_LOOKS.find((l) => l.id === id)!.label}</span>
        )}
      />
      <p className="text-[11px] leading-relaxed text-fg-subtle">{current.hint}</p>
    </div>
  );
}

/** Denoise + 2x upscale + sharpen (classic filters, CPU, ~1 s). */
export function EnhanceToggle({ checked, onChange }: { checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <Switch
      label="Enhance (2x size)"
      description="Light denoise, 2x upscale and a gentle sharpen with ffmpeg. About a second; it does not invent detail like an AI upscaler."
      checked={checked}
      onChange={onChange}
    />
  );
}
