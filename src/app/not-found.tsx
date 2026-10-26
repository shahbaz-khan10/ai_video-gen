import { Compass } from "lucide-react";
import { Logo } from "@/components/brand/logo";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";

export default function NotFound() {
  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center gap-8 px-4 py-16">
      <Logo />
      <EmptyState
        icon={Compass}
        title="This page doesn't exist"
        description="The link may be broken or the page may have moved."
        action={
          <div className="flex flex-wrap justify-center gap-2">
            <ButtonLink href="/dashboard" size="sm">
              Go to Studio
            </ButtonLink>
            <ButtonLink href="/" variant="secondary" size="sm">
              Home
            </ButtonLink>
          </div>
        }
      />
    </main>
  );
}
