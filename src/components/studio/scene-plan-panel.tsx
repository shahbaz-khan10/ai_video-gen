"use client";

import { AlertTriangle, Ban, CheckCircle2, CircleDashed, Clapperboard, Plus, Scissors, Trash2 } from "lucide-react";
import { cn } from "@/lib/cn";
import type { CompiledPrompt, GenerationPlan, InstructionStatus, SceneInput } from "@/types/api";

const STATUS: Record<InstructionStatus, { icon: typeof CheckCircle2; className: string; label: string }> = {
  included: { icon: CheckCircle2, className: "text-emerald-300", label: "Understood and included" },
  compressed: { icon: CircleDashed, className: "text-amber-300", label: "Understood but compressed" },
  unsupported: { icon: Ban, className: "text-fg-subtle", label: "Not supported by the model" },
  omitted_budget: { icon: Scissors, className: "text-red-300", label: "Not included because of the token budget" },
};

const COMPONENT_TONE = {
  included: "text-fg-muted",
  compressed: "text-amber-300",
  omitted: "text-red-300 line-through",
} as const;

/** The exact prompt a model receives, with its measured token count and what was compressed or left out. */
function CompiledPromptView({ prompt }: { prompt: CompiledPrompt }) {
  const changed = prompt.components.filter((c) => c.status !== "included");
  return (
    <details className="rounded-lg border border-line bg-ink-950 p-2.5 text-xs">
      <summary className="flex cursor-pointer flex-wrap items-center justify-between gap-2 text-fg">
        <span className="capitalize">{prompt.target}</span>
        <span className="font-mono text-[10px] text-fg-subtle">
          {prompt.tokens} / {prompt.budget} tokens · {prompt.model}
          {prompt.measured ? "" : " · estimated"}
          {changed.length ? ` · ${changed.length} shortened` : ""}
        </span>
      </summary>
      <p className="mt-2 whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-fg-muted">{prompt.text}</p>
      <ul className="mt-2 flex flex-wrap gap-1.5">
        {prompt.components.map((c) => (
          <li
            key={c.name}
            title={c.status === "included" ? c.text : `Full: ${c.full_text}`}
            className={cn("rounded border border-line px-1.5 py-0.5 font-mono text-[10px]", COMPONENT_TONE[c.status])}
          >
            {c.name}: {c.status}
          </li>
        ))}
      </ul>
    </details>
  );
}

type ScenePlanPanelProps = {
  plan: GenerationPlan;
  /** Long videos: the editable scene list sent with the request. */
  scenes: SceneInput[] | null;
  totalSeconds: number | null;
  onScenesChange: (scenes: SceneInput[]) => void;
};

/** Shows how the backend understood the prompt, honestly, and lets the user edit a long video's scenes. */
export function ScenePlanPanel({ plan, scenes, totalSeconds, onScenesChange }: ScenePlanPanelProps) {
  const env = plan.environment;
  const place = [env.location, env.time_of_day, env.weather, env.lighting].filter(Boolean).join(" · ");
  const camera = [plan.camera.movement, plan.camera.shot_type, plan.camera.angle].filter(Boolean).join(" · ");
  const assigned = scenes?.reduce((sum, s) => sum + (s.duration_seconds ?? 0), 0) ?? 0;

  const update = (i: number, patch: Partial<SceneInput>) =>
    scenes && onScenesChange(scenes.map((s, k) => (k === i ? { ...s, ...patch } : s)));

  return (
    <section aria-label="Scene plan" className="flex flex-col gap-4 rounded-xl border border-line bg-ink-900 p-4 text-sm">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-medium text-fg">How your prompt was understood</h3>
        <span className="font-mono text-[10px] text-fg-subtle">{plan.planner}</span>
      </div>

      <dl className="grid gap-2 text-xs">
        {plan.characters.length > 0 && (
          <div>
            <dt className="text-fg-subtle">Characters{plan.people_count ? ` · ${plan.people_count} people` : ""}</dt>
            <dd className="mt-1 flex flex-col gap-1">
              {plan.characters.map((c) => (
                <span key={c.id} className="text-fg-muted">
                  <span className="text-fg">
                    {c.count && c.count > 1 ? `${c.count} × ` : ""}
                    {c.description || c.id}
                  </span>
                  {[c.clothing && `wearing ${c.clothing}`, c.position, c.action].filter(Boolean).map((d) => ` · ${d}`)}
                </span>
              ))}
            </dd>
          </div>
        )}
        {place && (
          <div>
            <dt className="text-fg-subtle">Place</dt>
            <dd className="mt-1 text-fg-muted">{place}</dd>
          </div>
        )}
        {camera && (
          <div>
            <dt className="text-fg-subtle">Camera</dt>
            <dd className="mt-1 text-fg-muted">{camera}</dd>
          </div>
        )}
      </dl>

      <div>
        <p className="text-xs text-fg-subtle">Your instructions</p>
        <ul className="mt-1.5 flex flex-col gap-1.5">
          {plan.instructions.map((ins, k) => {
            const s = STATUS[ins.status] ?? STATUS.included;
            const Icon = s.icon;
            return (
              <li key={`${k}-${ins.text}`} className="flex gap-2 text-xs text-fg-muted">
                <Icon className={cn("mt-0.5 size-3.5 shrink-0", s.className)} aria-hidden />
                <span>
                  <span className="text-fg">{ins.text}</span>
                  <span className={cn("block text-[11px]", s.className)}>
                    {s.label}
                    {ins.targets && ins.targets.length > 0 && ins.status !== "unsupported" ? ` · ${ins.targets.join(", ")}` : ""}
                  </span>
                  {ins.note && <span className="block text-[11px] text-fg-subtle">{ins.note}</span>}
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      {plan.limitations.length > 0 && (
        <div className="rounded-lg border border-amber-300/25 bg-amber-300/[0.05] p-3">
          <p className="flex items-center gap-1.5 text-xs font-medium text-amber-200">
            <AlertTriangle className="size-3.5" aria-hidden />
            What the models can&apos;t do reliably
          </p>
          <ul className="mt-1.5 list-disc space-y-1 pl-4 text-xs text-fg-muted">
            {plan.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </div>
      )}

      {scenes && totalSeconds && (
        <div>
          <div className="flex items-center justify-between">
            <p className="flex items-center gap-1.5 text-xs text-fg-subtle">
              <Clapperboard className="size-3.5" aria-hidden />
              Scenes · edit before generating
            </p>
            <span className={cn("font-mono text-[10px]", Math.abs(assigned - totalSeconds) > 0.5 ? "text-amber-300" : "text-fg-subtle")}>
              {assigned.toFixed(0)}s of {totalSeconds}s{Math.abs(assigned - totalSeconds) > 0.5 ? " · scaled to fit" : ""}
            </span>
          </div>
          <ol className="mt-2 flex flex-col gap-2">
            {scenes.map((scene, i) => (
              <li key={i} className="flex gap-2">
                <span className="mt-2 w-5 shrink-0 font-mono text-[10px] text-fg-subtle">{i + 1}</span>
                <textarea
                  aria-label={`Scene ${i + 1} description`}
                  value={scene.description}
                  maxLength={600}
                  rows={2}
                  onChange={(e) => update(i, { description: e.target.value })}
                  className="min-h-14 flex-1 resize-y rounded-lg border border-line bg-ink-950 px-2.5 py-1.5 text-xs text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/40"
                />
                <label className="flex w-16 shrink-0 flex-col text-[10px] text-fg-subtle">
                  seconds
                  <input
                    type="number"
                    min={2}
                    max={120}
                    value={scene.duration_seconds ?? ""}
                    onChange={(e) => update(i, { duration_seconds: e.target.value ? Number(e.target.value) : undefined })}
                    className="mt-0.5 h-8 rounded-md border border-line bg-ink-950 px-1.5 text-xs text-fg"
                  />
                </label>
                <button
                  type="button"
                  aria-label={`Remove scene ${i + 1}`}
                  disabled={scenes.length <= 1}
                  onClick={() => onScenesChange(scenes.filter((_, k) => k !== i))}
                  className="mt-1 grid size-7 place-items-center rounded-md text-fg-subtle hover:bg-white/5 hover:text-fg disabled:opacity-30"
                >
                  <Trash2 className="size-3.5" aria-hidden />
                </button>
              </li>
            ))}
          </ol>
          <button
            type="button"
            disabled={scenes.length >= 24 || (totalSeconds ?? 0) / (scenes.length + 1) < 2}
            onClick={() => onScenesChange([...scenes, { description: "" }])}
            className="mt-2 flex items-center gap-1.5 text-xs text-violet-soft hover:text-fg disabled:opacity-40"
          >
            <Plus className="size-3.5" aria-hidden />
            Add scene
          </button>
        </div>
      )}

      {plan.compiled && plan.compiled.length > 0 ? (
        <div>
          <p className="text-xs text-fg-subtle">
            Exact prompt{plan.compiled.length > 1 ? "s" : ""} sent to the model
            {scenes ? " (scene edits are compiled again when you generate)" : ""}
          </p>
          <div className="mt-1.5 flex flex-col gap-1.5">
            {plan.compiled.map((p) => (
              <CompiledPromptView key={p.target} prompt={p} />
            ))}
          </div>
        </div>
      ) : (
        plan.model_prompt &&
        !scenes && (
          <details className="text-xs">
            <summary className="cursor-pointer text-fg-subtle">Exact prompt sent to the model</summary>
            <p className="mt-1.5 whitespace-pre-wrap font-mono text-[11px] text-fg-muted">{plan.model_prompt}</p>
          </details>
        )
      )}
    </section>
  );
}
