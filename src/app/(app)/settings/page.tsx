import type { Metadata } from "next";
import { PageContainer } from "@/components/layout/page-container";
import { PageHeader } from "@/components/layout/page-header";
import { PreferencesForm, SettingsSection } from "@/components/settings/preferences-form";
import { UserAvatar } from "@/components/ui/user-avatar";
import { MOCK_USER } from "@/lib/mock-data";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <PageContainer>
      <PageHeader title="Settings" description="Interface preferences for this session. Changes apply immediately." />

      <div className="mt-8">
        <SettingsSection title="Profile" description="How you appear across the studio.">
          <div className="flex items-center gap-4">
            <UserAvatar initials={MOCK_USER.initials} size="lg" />
            <div>
              <p className="text-sm font-medium text-fg">{MOCK_USER.name}</p>
              <p className="text-xs text-fg-subtle">Placeholder profile · sign-in is not available yet</p>
            </div>
          </div>
        </SettingsSection>

        <SettingsSection title="Models" description="Connections to image and video models.">
          <p className="text-sm leading-relaxed text-fg-muted">
            Text to Image uses an open-weight model (SD-Turbo by default) running on the backend machine. No API
            keys are stored or required. The model is configured with IMAGE_* settings in backend/.env. Video models
            arrive in a later phase.
          </p>
        </SettingsSection>

        <PreferencesForm />
      </div>
    </PageContainer>
  );
}
