import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { notFound } from "next/navigation";
import { ArrowLeft, Info, WandSparkles } from "lucide-react";
import { PageContainer } from "@/components/layout/page-container";
import { ProjectThumbnail } from "@/components/projects/project-thumbnail";
import { ButtonLink } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { SkeletonBlock } from "@/components/ui/loading-state";
import { SampleBadge } from "@/components/ui/section-heading";
import { getProject, MOCK_PROJECTS } from "@/lib/mock-data";
import { ASPECT_RATIOS, getMode, getStyle } from "@/lib/studio-options";

export function generateStaticParams() {
  return MOCK_PROJECTS.map((p) => ({ id: p.id }));
}

export async function generateMetadata({ params }: PageProps<"/projects/[id]">): Promise<Metadata> {
  const { id } = await params;
  return { title: getProject(id)?.title ?? "Project not found" };
}

export default function ProjectDetailPage({ params }: PageProps<"/projects/[id]">) {
  return (
    <PageContainer>
      <Link
        href="/projects"
        className="group inline-flex items-center gap-1.5 rounded text-sm text-fg-muted transition-colors hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
      >
        <ArrowLeft className="size-4 transition-transform group-hover:-translate-x-0.5" aria-hidden />
        My Projects
      </Link>
      {/* The project depends on URL data, so it streams in behind the static shell. */}
      <Suspense fallback={<ProjectDetailSkeleton />}>
        <ProjectDetail params={params} />
      </Suspense>
    </PageContainer>
  );
}

function ProjectDetailSkeleton() {
  return (
    <div role="status" aria-label="Loading project">
      <SkeletonBlock className="mt-6 h-16 max-w-md" />
      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <SkeletonBlock className="aspect-video rounded-2xl" />
        <div className="flex flex-col gap-4">
          <SkeletonBlock className="h-36" />
          <SkeletonBlock className="h-56" />
        </div>
      </div>
    </div>
  );
}

async function ProjectDetail({ params }: { params: PageProps<"/projects/[id]">["params"] }) {
  const { id } = await params;
  const project = getProject(id);
  if (!project) notFound();

  const mode = getMode(project.mode);
  const ModeIcon = mode.icon;
  const style = getStyle(project.styleId);
  const ratio = ASPECT_RATIOS.find((r) => r.id === project.aspectRatio)!;

  const settings = [
    ["Mode", mode.label],
    ["Aspect ratio", `${ratio.id} · ${ratio.label}`],
    ["Visual style", style.label],
    ...(project.duration ? [["Clip length", project.duration]] : []),
    ["Created", project.created],
    ["Last edited", project.updated],
  ];

  return (
    <>
      <div className="mt-6 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <div className="mb-2 flex items-center gap-2 text-sm text-fg-subtle">
            <ModeIcon className="size-4 text-violet-soft" aria-hidden />
            {mode.label}
            <SampleBadge />
          </div>
          <h1 className="text-balance text-2xl font-semibold tracking-[-0.03em] text-fg sm:text-3xl">{project.title}</h1>
        </div>
        <ButtonLink href={`/create?project=${project.id}`} size="lg" className="w-full sm:w-auto">
          <WandSparkles className="size-4" aria-hidden />
          Open in Create
        </ButtonLink>
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <figure className="self-start overflow-hidden rounded-2xl border border-line bg-ink-900">
          <ProjectThumbnail project={project} />
          <figcaption className="flex items-start gap-2 border-t border-line px-4 py-3 text-xs text-fg-muted">
            <Info className="mt-px size-3.5 shrink-0 text-fg-subtle" aria-hidden />
            Placeholder artwork. No image or video has been generated for this sample project.
          </figcaption>
        </figure>

        <div className="flex flex-col gap-4">
          <section aria-labelledby="prompt-heading" className="rounded-xl border border-line bg-ink-900 p-4">
            <div className="mb-2 flex items-center justify-between">
              <h2 id="prompt-heading" className="text-[13px] font-medium text-fg">
                Prompt
              </h2>
              <CopyButton text={project.prompt} />
            </div>
            <p className="text-sm leading-relaxed text-fg-muted">{project.prompt}</p>
          </section>

          <section aria-labelledby="settings-heading" className="rounded-xl border border-line bg-ink-900 p-4">
            <h2 id="settings-heading" className="mb-1 text-[13px] font-medium text-fg">
              Settings
            </h2>
            <dl className="divide-y divide-line">
              {settings.map(([k, v]) => (
                <div key={k} className="flex items-center justify-between gap-4 py-2.5 text-sm">
                  <dt className="text-fg-muted">{k}</dt>
                  <dd className="text-right text-fg">{v}</dd>
                </div>
              ))}
            </dl>
          </section>

          <p className="text-xs leading-relaxed text-fg-subtle">
            Renaming, downloads and version history arrive once projects can be saved. &ldquo;Open in Create&rdquo; loads
            this project&apos;s prompt and settings into the workspace.
          </p>
        </div>
      </div>
    </>
  );
}
