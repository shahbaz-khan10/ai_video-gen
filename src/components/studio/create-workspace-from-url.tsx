"use client";

import { useSearchParams } from "next/navigation";
import { usePreferences } from "@/components/providers/preferences-provider";
import { SkeletonBlock } from "@/components/ui/loading-state";
import { getProject } from "@/lib/mock-data";
import { EXAMPLE_PROMPT, isMode, VISUAL_STYLES } from "@/lib/studio-options";
import type { CreateDraft } from "@/types/studio";
import { CreateWorkspace } from "./create-workspace";

/**
 * Builds the workspace's starting values. Priority: a project opened via
 * `?project=`, then `?mode=` / `?style=`, then the session defaults from Settings.
 */
export function CreateWorkspaceFromUrl() {
  const params = useSearchParams();
  const { preferences } = usePreferences();
  const project = getProject(params.get("project") ?? "");
  const modeParam = params.get("mode");
  const styleParam = VISUAL_STYLES.find((s) => s.id === params.get("style"))?.id;

  const initial: CreateDraft = project
    ? {
        mode: project.mode,
        prompt: project.prompt,
        aspectRatio: project.aspectRatio,
        styleId: project.styleId,
        duration: project.duration ?? "6s",
      }
    : {
        mode: isMode(modeParam) ? modeParam : preferences.defaultMode,
        prompt: EXAMPLE_PROMPT,
        aspectRatio: preferences.defaultAspectRatio,
        styleId: styleParam ?? preferences.defaultStyleId,
        duration: "6s",
      };

  // Next keeps visited pages mounted (hidden) between navigations, so remount
  // whenever the starting values change rather than keeping a stale draft.
  const draftKey = [params.toString(), initial.mode, initial.aspectRatio, initial.styleId].join("|");

  return (
    <CreateWorkspace
      key={draftKey}
      initial={initial}
      sourceProject={project ? { id: project.id, title: project.title } : undefined}
    />
  );
}

export function CreateWorkspaceSkeleton() {
  return (
    <div
      className="grid gap-6 lg:grid-cols-[minmax(0,400px)_minmax(0,1fr)] xl:grid-cols-[minmax(0,440px)_minmax(0,1fr)]"
      role="status"
      aria-label="Loading workspace"
    >
      <div className="flex flex-col gap-6">
        {["h-[52px]", "h-[200px]", "h-[92px]", "h-[120px]", "h-[64px]"].map((h) => (
          <SkeletonBlock key={h} className={h} />
        ))}
      </div>
      <SkeletonBlock className="min-h-[380px] rounded-2xl lg:min-h-[680px]" />
    </div>
  );
}
