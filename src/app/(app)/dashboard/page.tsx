import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Layers, Plus } from "lucide-react";
import { Reveal } from "@/components/motion/reveal";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ModeShortcuts } from "@/components/studio/mode-shortcuts";
import { PageContainer } from "@/components/layout/page-container";
import { PageHeader } from "@/components/layout/page-header";
import { BackendStatusCard } from "@/components/system/backend-status";
import { ProjectCard } from "@/components/projects/project-card";
import { SampleBadge, SectionHeading } from "@/components/ui/section-heading";
import { MOCK_PROJECTS, MOCK_USER } from "@/lib/mock-data";

export const metadata: Metadata = { title: "Overview" };

export default function StudioOverviewPage() {
  const recent = MOCK_PROJECTS.slice(0, 3);

  return (
    <PageContainer>
      <PageHeader
        eyebrow={`Welcome back, ${MOCK_USER.name}`}
        title="Your Creative Studio"
        description="Pick up where you left off, or start a new scene from a prompt or a reference image."
        actions={
          <ButtonLink href="/create" size="lg" className="w-full sm:w-auto">
            <Plus className="size-4" aria-hidden />
            Create New
          </ButtonLink>
        }
      />

      <Reveal delay={0.05} className="mt-10">
        <SectionHeading title="Start something new" />
        <ModeShortcuts />
      </Reveal>

      <Reveal delay={0.1} className="mt-12">
        <SectionHeading
          title="Recent projects"
          aside={
            <div className="flex items-center gap-3">
              <SampleBadge />
              <Link
                href="/projects"
                className="group flex items-center gap-1 rounded text-sm text-fg-muted transition-colors hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
              >
                View all
                <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
              </Link>
            </div>
          }
        />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {recent.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      </Reveal>

      <Reveal delay={0.15} className="mt-12 grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex flex-col">
          <SectionHeading title="Generation queue" />
          <EmptyState
            icon={Layers}
            title="Nothing rendering yet"
            description="Images you generate in Create are not saved to projects yet. Project history arrives in a later phase."
            action={
              <ButtonLink href="/create" variant="secondary" size="sm">
                Draft a prompt
              </ButtonLink>
            }
            className="flex-1"
          />
        </div>
        <div>
          <SectionHeading title="System" />
          <BackendStatusCard />
        </div>
      </Reveal>
    </PageContainer>
  );
}
