"use client";

import { useSearchParams } from "next/navigation";
import { isMode } from "@/lib/studio-options";
import { CreateWorkspace } from "./create-workspace";

/** Reads `?mode=` so dashboard shortcuts can open the workspace in a given mode. */
export function CreateWorkspaceFromUrl() {
  const param = useSearchParams().get("mode");
  const mode = isMode(param) ? param : undefined;
  return <CreateWorkspace key={mode ?? "default"} initialMode={mode} />;
}

export function CreateWorkspaceSkeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,400px)_minmax(0,1fr)] xl:grid-cols-[minmax(0,440px)_minmax(0,1fr)]" aria-busy="true" aria-label="Loading workspace">
      <div className="flex flex-col gap-6">
        {[52, 200, 92, 120, 64].map((h, i) => (
          <div key={i} className="animate-pulse rounded-xl bg-ink-900" style={{ height: h }} />
        ))}
      </div>
      <div className="min-h-[380px] animate-pulse rounded-2xl bg-ink-900 lg:min-h-[680px]" />
    </div>
  );
}
