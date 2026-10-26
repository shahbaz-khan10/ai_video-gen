import type { Metadata } from "next";
import { Plus } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import { PageContainer } from "@/components/layout/page-container";
import { PageHeader } from "@/components/layout/page-header";
import { ProjectLibrary } from "@/components/projects/project-library";
import { SampleBadge } from "@/components/ui/section-heading";
import { MOCK_PROJECTS } from "@/lib/mock-data";

export const metadata: Metadata = { title: "My Projects" };

export default function ProjectsPage() {
  return (
    <PageContainer>
      <PageHeader
        title="My Projects"
        description="Every scene you have drafted, in one place. These cards are sample data until projects can be saved."
        actions={
          <>
            <SampleBadge />
            <ButtonLink href="/create">
              <Plus className="size-4" aria-hidden />
              Create New
            </ButtonLink>
          </>
        }
      />
      <div className="mt-8">
        <ProjectLibrary projects={MOCK_PROJECTS} />
      </div>
    </PageContainer>
  );
}
