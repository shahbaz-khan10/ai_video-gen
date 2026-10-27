"use client";

import { useEffect, useState } from "react";
import { DEFAULT_IMAGE_CAPABILITIES, type ImageCapabilities } from "@/lib/studio-options";
import { api } from "./client";

/**
 * Resolutions and step presets of the backend's image model, from /info.
 * Until it answers (or if it is offline) the defaults that match the backend's default model are used.
 */
export function useImageCapabilities(): ImageCapabilities {
  const [capabilities, setCapabilities] = useState(DEFAULT_IMAGE_CAPABILITIES);

  useEffect(() => {
    let cancelled = false;
    api
      .info()
      .then(({ limits, generation }) => {
        if (cancelled || limits.image_resolutions.length === 0) return;
        setCapabilities({
          modelId: generation.model_id,
          resolutions: limits.image_resolutions,
          defaultResolution: limits.image_default_resolution,
          stepPresets: limits.image_step_presets,
          defaultSteps: limits.image_default_steps,
        });
      })
      .catch(() => {
        // Offline: keep the defaults. Generate will report the connection problem.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return capabilities;
}
