"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Search, SearchX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { getStyle, isVideoMode } from "@/lib/studio-options";
import type { Project } from "@/types/studio";
import { cn } from "@/lib/cn";
import { ProjectCard } from "./project-card";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "image", label: "Images" },
  { id: "video", label: "Videos" },
] as const;

type Filter = (typeof FILTERS)[number]["id"];

function matches(project: Project, filter: Filter, query: string) {
  const isVideo = isVideoMode(project.mode);
  if (filter === "image" && isVideo) return false;
  if (filter === "video" && !isVideo) return false;
  const q = query.trim().toLowerCase();
  return !q || `${project.title} ${getStyle(project.styleId).label} ${project.prompt}`.toLowerCase().includes(q);
}

export function ProjectLibrary({ projects }: { projects: Project[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const visible = projects.filter((p) => matches(p, filter, query));

  return (
    <div>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div role="group" aria-label="Filter by type" className="flex gap-1 rounded-lg border border-line bg-ink-900 p-1">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              aria-pressed={filter === f.id}
              onClick={() => setFilter(f.id)}
              className={cn(
                "rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70",
                filter === f.id ? "bg-ink-700 text-fg" : "text-fg-muted hover:text-fg",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <label className="relative block sm:w-72">
          <span className="sr-only">Search projects</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-fg-subtle" aria-hidden />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search projects"
            className="h-10 w-full rounded-lg border border-line bg-ink-900 pl-9 pr-3 text-sm text-fg placeholder:text-fg-subtle transition-colors hover:border-line-strong focus-visible:border-violet-soft/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/40"
          />
        </label>
      </div>

      <p className="sr-only" aria-live="polite">
        {visible.length} {visible.length === 1 ? "project" : "projects"} shown
      </p>

      <div className="mt-6">
        {visible.length === 0 ? (
          <EmptyState
            icon={SearchX}
            title="No projects match"
            description="Try a different search term or switch the filter back to All."
            action={
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setQuery("");
                  setFilter("all");
                }}
              >
                Reset filters
              </Button>
            }
          />
        ) : (
          <motion.ul layout className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <AnimatePresence initial={false}>
              {visible.map((project) => (
                <motion.li
                  key={project.id}
                  layout
                  initial={{ opacity: 0, scale: 0.97 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.97 }}
                  transition={{ duration: 0.25 }}
                >
                  <ProjectCard project={project} />
                </motion.li>
              ))}
            </AnimatePresence>
          </motion.ul>
        )}
      </div>
    </div>
  );
}
