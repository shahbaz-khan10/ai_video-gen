import Link from "next/link";
import { ArrowUpRight, Clock } from "lucide-react";
import { getMode, getStyle } from "@/lib/studio-options";
import type { Project } from "@/types/studio";
import { ProjectThumbnail } from "./project-thumbnail";

export function ProjectCard({ project }: { project: Project }) {
  const mode = getMode(project.mode);
  const ModeIcon = mode.icon;

  return (
    <Link
      href={`/projects/${project.id}`}
      className="group relative block overflow-hidden rounded-xl border border-line bg-ink-900 transition-[border-color,transform,box-shadow] duration-300 hover:-translate-y-0.5 hover:border-line-strong hover:shadow-[0_20px_50px_-24px_rgb(0_0_0/0.9)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
    >
      <article>
        <ProjectThumbnail project={project} className="border-b border-line">
          <span
            aria-hidden
            className="absolute inset-0 grid place-items-center bg-black/20 opacity-0 transition-opacity duration-300 group-hover:opacity-100 group-focus-visible:opacity-100"
          >
            <span className="flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1.5 text-xs font-medium text-white backdrop-blur-md">
              Open project
              <ArrowUpRight className="size-3.5" />
            </span>
          </span>
        </ProjectThumbnail>

        <div className="p-4">
          <h3 className="truncate text-sm font-medium text-fg">{project.title}</h3>
          <div className="mt-2 flex items-center justify-between gap-2 text-xs text-fg-subtle">
            <span className="flex min-w-0 items-center gap-1.5">
              <ModeIcon className="size-3.5 shrink-0" aria-hidden />
              <span className="truncate">
                {mode.label}
                <span aria-hidden> · </span>
                {getStyle(project.styleId).label}
              </span>
            </span>
            <span className="flex shrink-0 items-center gap-1">
              <Clock className="size-3" aria-hidden />
              {project.updated}
            </span>
          </div>
        </div>
      </article>
    </Link>
  );
}
