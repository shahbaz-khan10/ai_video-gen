import { FolderX } from "lucide-react";
import { PageContainer } from "@/components/layout/page-container";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";

export default function ProjectNotFound() {
  return (
    <PageContainer>
      <EmptyState
        icon={FolderX}
        title="Project not found"
        description="This project doesn't exist or was removed. Pick one from your library instead."
        action={<ButtonLink href="/projects" variant="secondary" size="sm">Back to My Projects</ButtonLink>}
        className="mt-10"
      />
    </PageContainer>
  );
}
