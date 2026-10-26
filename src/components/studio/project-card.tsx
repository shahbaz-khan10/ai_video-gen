import { Clock, Play } from "lucide-react";
import { Poster } from "@/components/ui/poster";
import type { Project } from "@/lib/mock-data";
import { MODES } from "@/lib/studio-options";

const RATIO_CLASS: Record<Project["aspectRatio"], string> = {
  "16:9": "aspect-video w-full",
  "9:16": "aspect-[9/16] h-full",
  "1:1": "aspect-square h-full",
};

export function ProjectCard({ project }: { project: Project }) {
  const mode = MODES.find((m) => m.id === project.mode)!;
  const ModeIcon = mode.icon;
  const isVideo = project.mode !== "text-to-image";

  return (
    <article className="group relative overflow-hidden rounded-xl border border-line bg-ink-900 transition-[border-color,transform,box-shadow] duration-300 focus-within:border-line-strong hover:-translate-y-0.5 hover:border-line-strong hover:shadow-[0_20px_50px_-24px_rgb(0_0_0/0.9)]">
      {/* Thumbnail stage keeps every card the same height regardless of ratio */}
      <div className="relative flex aspect-video items-center justify-center overflow-hidden border-b border-line bg-ink-950">
        {project.aspectRatio !== "16:9" && (
          <Poster tone={project.tone} position="absolute" className="inset-0 scale-110 opacity-35 blur-xl" />
        )}
        <Poster
          tone={project.tone}
          className={`${RATIO_CLASS[project.aspectRatio]} transition-transform duration-500 ease-out group-hover:scale-[1.04]`}
        />
        {isVideo && (
          <span className="absolute inset-0 grid place-items-center opacity-0 transition-opacity duration-300 group-hover:opacity-100" aria-hidden>
            <span className="grid size-11 place-items-center rounded-full bg-white/15 backdrop-blur-md">
              <Play className="ml-0.5 size-4 fill-white text-white" />
            </span>
          </span>
        )}
        <span className="absolute left-2.5 top-2.5 rounded-md bg-black/45 px-1.5 py-0.5 font-mono text-[10px] text-white/85 backdrop-blur">
          {project.aspectRatio}
        </span>
        {project.duration && (
          <span className="absolute bottom-2.5 right-2.5 rounded-md bg-black/45 px-1.5 py-0.5 font-mono text-[10px] text-white/85 backdrop-blur">
            {project.duration}
          </span>
        )}
      </div>

      <div className="p-4">
        <h3 className="truncate text-sm font-medium text-fg">{project.title}</h3>
        <div className="mt-2 flex items-center justify-between gap-2 text-xs text-fg-subtle">
          <span className="flex items-center gap-1.5">
            <ModeIcon className="size-3.5" aria-hidden />
            {mode.label}
            <span aria-hidden>·</span>
            {project.style}
          </span>
          <span className="flex shrink-0 items-center gap-1">
            <Clock className="size-3" aria-hidden />
            {project.updated}
          </span>
        </div>
      </div>
    </article>
  );
}
