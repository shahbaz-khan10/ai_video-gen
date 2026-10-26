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
        description="Choose a mode, describe your shot, and set the frame and look. Generation will be enabled once a model is connected."
      />
      <div className="mt-8">
        <Suspense fallback={<CreateWorkspaceSkeleton />}>
          <CreateWorkspaceFromUrl />
        </Suspense>
      </div>
    </PageContainer>
  );
}
