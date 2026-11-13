"use client";

import { useId, useState } from "react";
import { ChevronDown, ChevronRight, Eraser, Lightbulb, ShieldAlert, Sparkles } from "lucide-react";
import { InfoHint } from "@/components/ui/info-hint";
import { EXAMPLE_PROMPT } from "@/lib/studio-options";
import type { GenerationMode } from "@/types/studio";
import { cn } from "@/lib/cn";

export const PROMPT_MAX = 4000; // must match PROMPT_MAX_CHARS in backend/app/schemas/generation.py

const PLACEHOLDERS: Record<GenerationMode, string> = {
  "text-to-image": "Describe the scene, people, their clothes, activities, lighting and camera lens…",
  "text-to-video": "Describe the scene, the action and how the camera moves…",
  "image-to-video": "Describe how the image should move: subject motion, camera, atmosphere…",
};

const LABELS: Record<GenerationMode, string> = {
  "text-to-image": "Prompt (Natural Language Scene)",
  "text-to-video": "Scene prompt",
  "image-to-video": "Motion prompt",
};

type PromptEditorProps = {
  mode: GenerationMode;
  value: string;
  onChange: (value: string) => void;
  negativePrompt?: string;
  onNegativePromptChange?: (value: string) => void;
  error?: string;
};

export function PromptEditor({
  mode,
  value,
  onChange,
  negativePrompt = "",
  onNegativePromptChange,
  error,
}: PromptEditorProps) {
  const id = useId();
  const countId = `${id}-count`;
  const errorId = `${id}-error`;
  const nearLimit = value.length > PROMPT_MAX * 0.9;
  const [showNegative, setShowNegative] = useState(Boolean(negativePrompt));

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label htmlFor={id} className="flex items-center gap-1.5 text-[13px] font-medium text-fg">
          {LABELS[mode]}
          <InfoHint label="Be specific about people count, clothing, actions, environment, lighting, and camera. The scene planning engine automatically structures your request." />
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
          rows={5}
          placeholder={PLACEHOLDERS[mode]}
          aria-invalid={Boolean(error)}
          aria-describedby={cn(countId, error && errorId)}
          className="block w-full resize-y rounded-xl bg-transparent px-4 pt-3.5 text-sm leading-relaxed text-fg placeholder:text-fg-subtle focus:outline-none"
        />
        <div className="flex items-center justify-between px-4 pb-3 pt-1">
          <p className="flex items-center gap-1 text-xs text-fg-subtle">
            <Sparkles className="size-3 text-violet-400" />
            Natural language scene comprehension active
          </p>
          <p id={countId} className={cn("font-mono text-[11px]", nearLimit ? "text-amber-300" : "text-fg-subtle")}>
            {value.length}/{PROMPT_MAX}
          </p>
        </div>
      </div>
      {error && (
        <p id={errorId} className="mt-1 text-xs text-red-300">
          {error}
        </p>
      )}

      {/* Negative Prompt toggle for text-to-image mode */}
      {mode === "text-to-image" && onNegativePromptChange && (
        <div className="rounded-xl border border-line/60 bg-ink-900/50 px-3.5 py-2.5">
          <button
            type="button"
            onClick={() => setShowNegative(!showNegative)}
            className="flex w-full items-center justify-between text-xs font-medium text-fg-muted transition-colors hover:text-fg"
          >
            <span className="flex items-center gap-1.5">
              <ShieldAlert className="size-3.5 text-amber-400/80" />
              Negative Prompt (Avoid unwanted elements)
            </span>
            {showNegative ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
          </button>
          {showNegative && (
            <div className="mt-2.5 space-y-1.5">
              <textarea
                value={negativePrompt}
                onChange={(e) => onNegativePromptChange(e.target.value)}
                rows={2}
                placeholder="Optional custom negative prompt (e.g. sunglasses, hats, darkness). Base anatomical protection is automatically applied."
                className="w-full rounded-lg border border-line bg-ink-950 px-3 py-2 text-xs text-fg placeholder:text-fg-subtle focus:border-violet-soft/50 focus:outline-none"
              />
              <p className="text-[11px] text-fg-subtle">
                Built-in engine filters repel plastic skin, deformed hands, extra limbs, and duplicate faces automatically.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
