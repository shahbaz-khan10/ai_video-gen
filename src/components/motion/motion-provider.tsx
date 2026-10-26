"use client";

import { MotionConfig } from "motion/react";
import type { ReactNode } from "react";
import { usePreferences } from "@/components/providers/preferences-provider";

/**
 * Applies global motion defaults. Follows the OS reduced-motion setting, and
 * the in-app "Reduce motion" preference can force it on.
 */
export function MotionProvider({ children }: { children: ReactNode }) {
  const { preferences } = usePreferences();
  return (
    <MotionConfig
      reducedMotion={preferences.reduceMotion ? "always" : "user"}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
    >
      <div data-reduce-motion={preferences.reduceMotion || undefined} className="contents">
        {children}
      </div>
    </MotionConfig>
  );
}
