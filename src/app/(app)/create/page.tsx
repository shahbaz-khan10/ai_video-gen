import type { Metadata } from "next";
import { Suspense } from "react";
import { PageContainer } from "@/components/layout/page-container";
import { PageHeader } from "@/components/layout/page-header";
import { CreateWorkspaceFromUrl, CreateWorkspaceSkeleton } from "@/components/studio/create-workspace-from-url";

export const metadata: Metadata = { title: "Create" };

export default function CreatePage() {
  return (
    <PageContainer width="wide">
      <PageHeader
        title="Create"
        description="Describe your shot and set the frame and look. Text to Image runs on a local open-weight model; video modes are coming soon."
      />
      <div className="mt-8">
        <Suspense fallback={<CreateWorkspaceSkeleton />}>
          <CreateWorkspaceFromUrl />
        </Suspense>
      </div>
    </PageContainer>
  );
}
