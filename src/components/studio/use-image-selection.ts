"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const ACCEPTED = ["image/png", "image/jpeg", "image/webp"] as const;
export type AcceptedImageType = (typeof ACCEPTED)[number];

export type SelectedImage = { url: string; name: string; size: number; type: AcceptedImageType };

export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

/**
 * Holds a locally selected image as an object URL. The file never leaves the
 * browser; URLs are revoked when replaced, cleared, or on unmount.
 */
export function useImageSelection() {
  const [image, setImage] = useState<SelectedImage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const urlRef = useRef<string | null>(null);

  const revoke = () => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    urlRef.current = null;
  };

  useEffect(() => revoke, []);

  const select = useCallback((file: File | undefined) => {
    if (!file) return;
    if (!isAccepted(file.type)) {
      setError("Please choose a PNG, JPG or WebP image.");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setError("That image is larger than 10 MB. Please choose a smaller file.");
      return;
    }
    revoke();
    const url = URL.createObjectURL(file);
    urlRef.current = url;
    setError(null);
    setImage({ url, name: file.name, size: file.size, type: file.type });
  }, []);

  const clear = useCallback(() => {
    revoke();
    setImage(null);
    setError(null);
  }, []);

  return { image, error, select, clear, accept: ACCEPTED.join(",") };
}

function isAccepted(type: string): type is AcceptedImageType {
  return (ACCEPTED as readonly string[]).includes(type);
}

export function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
