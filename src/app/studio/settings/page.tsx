import type { Metadata } from "next";
import type { ReactNode } from "react";
import { PageHeader, StudioPage } from "@/components/studio/page-header";
import { UserAvatar } from "@/components/studio/user-avatar";
import { MOCK_USER } from "@/lib/mock-data";

export const metadata: Metadata = { title: "Settings" };

function SettingsSection({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <section className="grid gap-4 border-t border-line py-8 md:grid-cols-[240px_1fr] md:gap-10">
      <div>
        <h2 className="text-sm font-medium text-fg">{title}</h2>
        <p className="mt-1 text-sm leading-relaxed text-fg-muted">{description}</p>
      </div>
      <div className="rounded-xl border border-line bg-ink-900 p-5">{children}</div>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5 text-sm">
      <dt className="text-fg-muted">{label}</dt>
      <dd className="text-right text-fg">{value}</dd>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <StudioPage>
      <PageHeader title="Settings" description="Workspace preferences. Editing is enabled once accounts are available." />

      <div className="mt-8">
        <SettingsSection title="Profile" description="How you appear across the studio.">
          <div className="flex items-center gap-4">
            <UserAvatar initials={MOCK_USER.initials} size="lg" />
            <div>
              <p className="text-sm font-medium text-fg">{MOCK_USER.name}</p>
              <p className="text-xs text-fg-subtle">Placeholder profile · sign-in not available yet</p>
            </div>
          </div>
        </SettingsSection>

        <SettingsSection title="Defaults" description="Starting values for new projects.">
          <dl className="divide-y divide-line">
            <Row label="Mode" value="Text to Video" />
            <Row label="Aspect ratio" value="16:9" />
            <Row label="Visual style" value="Cinematic" />
          </dl>
        </SettingsSection>

        <SettingsSection title="Models" description="Connections to image and video models.">
          <p className="text-sm leading-relaxed text-fg-muted">
            No models are connected. Model configuration arrives in a later phase; no API keys are stored
            or required in this preview.
          </p>
        </SettingsSection>

        <SettingsSection title="Accessibility" description="Motion and comfort.">
          <p className="text-sm leading-relaxed text-fg-muted">
            Animations follow your operating system&apos;s reduced-motion preference automatically.
          </p>
        </SettingsSection>
      </div>
    </StudioPage>
  );
}
