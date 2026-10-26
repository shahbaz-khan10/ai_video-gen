import type { ReactNode } from "react";
import { Poster } from "@/components/ui/poster";
import { cn } from "@/lib/cn";
import type { Project } from "@/types/studio";

const RATIO_CLASS: Record<Project["aspectRatio"], string> = {
  "16:9": "aspect-video w-full",
  "9:16": "aspect-[9/16] h-full",
  "1:1": "aspect-square h-full",
};

type ProjectThumbnailProps = {
  project: Project;
  className?: string;
  /** Extra overlay content, e.g. hover affordances. */
  children?: ReactNode;
};

/** 16:9 stage that letterboxes portrait and square artwork over a blurred backdrop. */
export function ProjectThumbnail({ project, className, children }: ProjectThumbnailProps) {
  return (
    <div className={cn("relative flex aspect-video items-center justify-center overflow-hidden bg-ink-950", className)}>
      {project.aspectRatio !== "16:9" && (
        <Poster tone={project.tone} position="absolute" className="inset-0 scale-110 opacity-35 blur-xl" />
      )}
      <Poster
        tone={project.tone}
        className={cn(RATIO_CLASS[project.aspectRatio], "transition-transform duration-500 ease-out group-hover:scale-[1.04]")}
      />
      <span className="absolute left-2.5 top-2.5 rounded-md bg-black/45 px-1.5 py-0.5 font-mono text-[10px] text-white/85 backdrop-blur">
        {project.aspectRatio}
      </span>
      {project.duration && (
        <span className="absolute bottom-2.5 right-2.5 rounded-md bg-black/45 px-1.5 py-0.5 font-mono text-[10px] text-white/85 backdrop-blur">
          {project.duration}
        </span>
      )}
      {children}
    </div>
  );
}
