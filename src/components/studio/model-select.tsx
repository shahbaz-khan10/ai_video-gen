"use client";

import { Cpu, Clock } from "lucide-react";
import { MODELS } from "@/lib/studio-options";
import { cn } from "@/lib/cn";
import { FieldLegend } from "./option-group";

/** Read-only: which model serves the current mode. The image model is configured on the backend (IMAGE_MODEL_ID). */
export function ModelInfo({ video }: { video: boolean }) {
  const model = video ? MODELS.video : MODELS.image;
  const Icon = video ? Clock : Cpu;
  return (
    <fieldset>
      <FieldLegend hint="Text-to-image runs on a local open-weight model. Video models are connected in a later phase.">
        Model
      </FieldLegend>
      <div className="flex items-center gap-3 rounded-lg border border-line bg-ink-900 px-3 py-2.5">
        <span
          className={cn(
            "grid size-8 shrink-0 place-items-center rounded-md border border-line-strong bg-ink-850",
            video ? "text-fg-subtle" : "text-violet-soft",
          )}
        >
          <Icon className="size-4" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="text-sm text-fg">{model.label}</p>
          <p className="truncate text-xs text-fg-subtle">{model.note}</p>
        </div>
      </div>
    </fieldset>
  );
}
