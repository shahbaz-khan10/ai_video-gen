"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { Preferences } from "@/types/studio";

export const DEFAULT_PREFERENCES: Preferences = {
  defaultMode: "text-to-video",
  defaultAspectRatio: "16:9",
  defaultStyleId: "cinematic",
  reduceMotion: false,
  startSidebarCollapsed: false,
};

type PreferencesContextValue = {
  preferences: Preferences;
  update: <K extends keyof Preferences>(key: K, value: Preferences[K]) => void;
  reset: () => void;
};

const PreferencesContext = createContext<PreferencesContextValue | null>(null);

/**
 * Holds interface preferences in memory. The root layout persists across
 * client-side navigation, so values last for the session and reset on reload.
 * Nothing is written to storage or sent anywhere.
 */
export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState<Preferences>(DEFAULT_PREFERENCES);

  const value = useMemo<PreferencesContextValue>(
    () => ({
      preferences,
      update: (key, next) => setPreferences((p) => ({ ...p, [key]: next })),
      reset: () => setPreferences(DEFAULT_PREFERENCES),
    }),
    [preferences],
  );

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences() {
  const ctx = useContext(PreferencesContext);
  if (!ctx) throw new Error("usePreferences must be used inside <PreferencesProvider>");
  return ctx;
}
