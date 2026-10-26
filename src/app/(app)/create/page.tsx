import type { Metadata } from "next";
import { Suspense } from "react";
import { CreateWorkspaceFromUrl, CreateWorkspaceSkeleton } from "@/components/create/create-workspace-from-url";
import { PageHeader } from "@/components/studio/page-header";

export const metadata: Metadata = { title: "Create" };

export default function CreatePage() {
  return (
    <div className="mx-auto w-full max-w-[1400px] px-4 py-8 sm:px-6 lg:px-10 lg:py-10">
      <PageHeader
        title="Create"
        description="Choose a mode, describe your shot, and set the frame and look. Generation will be enabled once a model is connected."
      />
      <div className="mt-8">
        <Suspense fallback={<CreateWorkspaceSkeleton />}>
          <CreateWorkspaceFromUrl />
        </Suspense>
      </div>
    </div>
  );
}
