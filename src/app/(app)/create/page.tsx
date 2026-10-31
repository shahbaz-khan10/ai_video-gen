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
        description="Text to Image runs on a local open-source model. Video modes are coming soon; for those you can set up the shot and check its settings."
      />
      <div className="mt-8">
        <Suspense fallback={<CreateWorkspaceSkeleton />}>
          <CreateWorkspaceFromUrl />
        </Suspense>
      </div>
    </PageContainer>
  );
}
