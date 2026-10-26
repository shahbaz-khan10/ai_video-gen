"use client";

import { useId } from "react";
import { Eraser, Lightbulb } from "lucide-react";
import { InfoHint } from "@/components/ui/info-hint";
import { EXAMPLE_PROMPT } from "@/lib/studio-options";
import type { GenerationMode } from "@/types/studio";
import { cn } from "@/lib/cn";

export const PROMPT_MAX = 1000;

const PLACEHOLDERS: Record<GenerationMode, string> = {
  "text-to-image": "Describe the subject, setting, light and lens…",
  "text-to-video": "Describe the scene, the action and how the camera moves…",
  "image-to-video": "Describe how the image should move: subject motion, camera, atmosphere…",
};

const LABELS: Record<GenerationMode, string> = {
  "text-to-image": "Prompt",
  "text-to-video": "Scene prompt",
  "image-to-video": "Motion prompt",
};

type PromptEditorProps = {
  mode: GenerationMode;
  value: string;
  onChange: (value: string) => void;
  error?: string;
};

export function PromptEditor({ mode, value, onChange, error }: PromptEditorProps) {
  const id = useId();
  const countId = `${id}-count`;
  const errorId = `${id}-error`;
  const nearLimit = value.length > PROMPT_MAX * 0.9;

  return (
    <div>
      <div className="mb-2.5 flex items-center justify-between">
        <label htmlFor={id} className="flex items-center gap-1.5 text-[13px] font-medium text-fg">
          {LABELS[mode]}
          <InfoHint label="Be specific about subject, lighting, lens and motion. Concrete details give more controllable results." />
        </label>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => onChange(EXAMPLE_PROMPT)}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-fg-muted transition-colors hover:bg-white/5 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
          >
            <Lightbulb className="size-3.5" aria-hidden />
            Use example
          </button>
          <button
            type="button"
            onClick={() => onChange("")}
            disabled={!value}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-fg-muted transition-colors hover:bg-white/5 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70 disabled:pointer-events-none disabled:opacity-40"
          >
            <Eraser className="size-3.5" aria-hidden />
            Clear
          </button>
        </div>
      </div>

      <div
        className={cn(
          "rounded-xl border bg-ink-900 transition-[border-color,box-shadow] duration-200 focus-within:border-violet-soft/50 focus-within:shadow-[0_0_0_4px_rgb(139_92_246/0.10)]",
          error ? "border-red-400/50" : "border-line",
        )}
      >
        <textarea
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          maxLength={PROMPT_MAX}
          rows={6}
          placeholder={PLACEHOLDERS[mode]}
          aria-invalid={Boolean(error)}
          aria-describedby={cn(countId, error && errorId)}
          className="block w-full resize-y rounded-xl bg-transparent px-4 pt-3.5 text-sm leading-relaxed text-fg placeholder:text-fg-subtle focus:outline-none"
        />
        <div className="flex items-center justify-between px-4 pb-3 pt-1">
          <p className="text-xs text-fg-subtle">Tip: name the lens and the light.</p>
          <p id={countId} className={cn("font-mono text-[11px]", nearLimit ? "text-amber-300" : "text-fg-subtle")}>
            {value.length}/{PROMPT_MAX}
          </p>
        </div>
      </div>
      {error && (
        <p id={errorId} className="mt-2 text-xs text-red-300">
          {error}
        </p>
      )}
    </div>
  );
}
