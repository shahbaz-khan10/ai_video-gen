"use client";

import type { ReactNode } from "react";
import { RotateCcw } from "lucide-react";
import { DEFAULT_PREFERENCES, usePreferences } from "@/components/providers/preferences-provider";
import { AspectRatioSelector } from "@/components/studio/aspect-ratio-selector";
import { OptionGroup } from "@/components/studio/option-group";
import { StyleSelector } from "@/components/studio/style-selector";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { MODES } from "@/lib/studio-options";

export function SettingsSection({ title, description, children }: { title: string; description: string; children: ReactNode }) {
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

/** Interface preferences. Stored in memory only, so they reset on reload. */
export function PreferencesForm() {
  const { preferences, update, reset } = usePreferences();
  const isDefault = (Object.keys(DEFAULT_PREFERENCES) as (keyof typeof DEFAULT_PREFERENCES)[]).every(
    (k) => preferences[k] === DEFAULT_PREFERENCES[k],
  );

  return (
    <>
      <SettingsSection
        title="Create defaults"
        description="What a new project starts with when you open Create. Links that pick a mode still override this."
      >
        <div className="flex flex-col gap-6">
          <OptionGroup
            legend="Default mode"
            options={MODES}
            value={preferences.defaultMode}
            onChange={(v) => update("defaultMode", v)}
            className="grid-cols-1 sm:grid-cols-3"
            renderOption={(id) => {
              const mode = MODES.find((m) => m.id === id)!;
              const Icon = mode.icon;
              return (
                <span className="flex items-center gap-2 px-3 py-2.5 text-[13px] font-medium">
                  <Icon className="size-4 shrink-0" aria-hidden />
                  {mode.label}
                </span>
              );
            }}
          />
          <AspectRatioSelector
            legend="Default aspect ratio"
            value={preferences.defaultAspectRatio}
            onChange={(v) => update("defaultAspectRatio", v)}
          />
          <StyleSelector
            legend="Default visual style"
            value={preferences.defaultStyleId}
            onChange={(v) => update("defaultStyleId", v)}
          />
        </div>
      </SettingsSection>

      <SettingsSection title="Interface" description="Motion and layout comfort.">
        <div className="flex flex-col gap-6">
          <Switch
            label="Reduce motion"
            description="Turns off animations across the app. Your operating system's reduced-motion setting is always respected too."
            checked={preferences.reduceMotion}
            onChange={(v) => update("reduceMotion", v)}
          />
          <Switch
            label="Collapse sidebar"
            description="Keeps the desktop sidebar narrow, showing icons with tooltips."
            checked={preferences.startSidebarCollapsed}
            onChange={(v) => update("startSidebarCollapsed", v)}
          />
        </div>
      </SettingsSection>

      <div className="flex flex-col gap-3 border-t border-line pt-6 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs leading-relaxed text-fg-subtle">
          These preferences apply right away for this session only. They are not saved, and reset when you reload or
          close the tab.
        </p>
        <Button variant="secondary" size="sm" onClick={reset} disabled={isDefault}>
          <RotateCcw className="size-3.5" aria-hidden />
          Reset to defaults
        </Button>
      </div>
    </>
  );
}
