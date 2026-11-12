"use client";

import { CheckCircle2, CircleAlert, CircleDashed, LoaderCircle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import type { SceneJob } from "@/types/api";

const ICON = {
  queued: { icon: CircleDashed, className: "text-fg-subtle" },
  processing: { icon: LoaderCircle, className: "animate-spin text-violet-soft" },
  completed: { icon: CheckCircle2, className: "text-emerald-300" },
  failed: { icon: CircleAlert, className: "text-red-300" },
} as const;

/** Per-scene status of a long video, from the server's real clip counts. Failed scenes can be retried alone. */
export function SceneProgress({
  scenes,
  canRetry,
  onRetry,
}: {
  scenes: SceneJob[];
  canRetry: boolean;
  onRetry: (index: number) => void;
}) {
  return (
    <ol aria-label="Scene progress" className="m-3 mt-0 flex flex-col gap-1.5 rounded-xl border border-line bg-ink-850 p-3">
      {scenes.map((scene) => {
        const { icon: Icon, className } = ICON[scene.status];
        return (
          <li key={scene.index} className="flex items-start gap-2 text-xs">
            <Icon className={cn("mt-0.5 size-3.5 shrink-0", className)} aria-label={scene.status} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-fg">
                {scene.index}. {scene.description}
              </p>
              <p className="font-mono text-[10px] text-fg-subtle">
                {scene.duration_seconds.toFixed(1)}s · {scene.clips_completed}/{scene.clips.length} clips
                {scene.error ? ` · ${scene.error.message}` : ""}
              </p>
            </div>
            {scene.status === "failed" && canRetry && (
              <Button variant="secondary" size="sm" onClick={() => onRetry(scene.index)}>
                <RotateCcw className="size-3.5" aria-hidden />
                Retry scene
              </Button>
            )}
          </li>
        );
      })}
    </ol>
  );
}
