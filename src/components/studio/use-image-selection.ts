"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api/client";

const ACCEPTED = ["image/png", "image/jpeg", "image/webp"] as const;
export type AcceptedImageType = (typeof ACCEPTED)[number];

export type SelectedImage = {
  url: string;
  name: string;
  size: number;
  type: AcceptedImageType;
  width: number;
  height: number;
  /** Set once the server has accepted and stored the image. */
  uploadId: string | null;
  uploading: boolean;
};

export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
export const MIN_IMAGE_SIDE = 256;
export const MAX_IMAGE_SIDE = 8192;

/**
 * Holds the image to animate: a local preview (object URL) plus the server upload it needs for generation.
 * Type, size and dimensions are checked here first; the server checks the bytes again. Object URLs are revoked
 * when replaced, cleared, or on unmount.
 */
export function useImageSelection() {
  const [image, setImage] = useState<SelectedImage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const urlRef = useRef<string | null>(null);
  const fileRef = useRef<File | null>(null);
  const selection = useRef(0);

  const revoke = () => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    urlRef.current = null;
  };

  useEffect(() => revoke, []);

  const upload = useCallback(async (file: File, id: number) => {
    try {
      const stored = await api.uploadImage(file);
      if (id !== selection.current) return;
      setImage((img) => (img ? { ...img, uploadId: stored.upload_id, uploading: false, width: stored.width, height: stored.height } : img));
    } catch (err) {
      if (id !== selection.current) return;
      setImage((img) => (img ? { ...img, uploading: false } : img));
      setError(err instanceof ApiError ? err.message : "The image could not be uploaded.");
    }
  }, []);

  const select = useCallback(
    async (file: File | undefined) => {
      if (!file) return;
      if (!isAccepted(file.type)) {
        setError("Please choose a JPG, PNG or WebP image.");
        return;
      }
      if (file.size > MAX_IMAGE_BYTES) {
        setError("That image is larger than 10 MB. Please choose a smaller file.");
        return;
      }
      const id = ++selection.current;
      const url = URL.createObjectURL(file);
      const size = await readSize(url);
      if (id !== selection.current) {
        URL.revokeObjectURL(url);
        return;
      }
      if (!size) {
        URL.revokeObjectURL(url);
        setError("This image is damaged or can't be read. Please choose another file.");
        return;
      }
      if (Math.min(size.width, size.height) < MIN_IMAGE_SIDE || Math.max(size.width, size.height) > MAX_IMAGE_SIDE) {
        URL.revokeObjectURL(url);
        setError(
          `The image is ${size.width}×${size.height}. Each side must be between ${MIN_IMAGE_SIDE} and ${MAX_IMAGE_SIDE} pixels.`,
        );
        return;
      }
      revoke();
      urlRef.current = url;
      fileRef.current = file;
      setError(null);
      setImage({ url, name: file.name, size: file.size, type: file.type as AcceptedImageType, ...size, uploadId: null, uploading: true });
      void upload(file, id);
    },
    [upload],
  );

  /** Uploads the same file again (e.g. after a network error or an expired upload). */
  const retryUpload = useCallback(() => {
    const file = fileRef.current;
    if (!file) return;
    const id = ++selection.current;
    setError(null);
    setImage((img) => (img ? { ...img, uploadId: null, uploading: true } : img));
    void upload(file, id);
  }, [upload]);

  const clear = useCallback(() => {
    selection.current += 1;
    revoke();
    fileRef.current = null;
    setImage(null);
    setError(null);
  }, []);

  return { image, error, select, clear, retryUpload, accept: ACCEPTED.join(",") };
}

function isAccepted(type: string): type is AcceptedImageType {
  return (ACCEPTED as readonly string[]).includes(type);
}

/** Decodes the image in the browser; null when it is corrupted or not an image. */
function readSize(url: string): Promise<{ width: number; height: number } | null> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img.naturalWidth > 0 ? { width: img.naturalWidth, height: img.naturalHeight } : null);
    img.onerror = () => resolve(null);
    img.src = url;
  });
}

/** The supported aspect ratio closest to the image's shape. */
export function nearestAspect(width: number, height: number): "16:9" | "9:16" | "1:1" {
  const r = width / height;
  const options: ["16:9" | "9:16" | "1:1", number][] = [["16:9", 16 / 9], ["9:16", 9 / 16], ["1:1", 1]];
  return options.reduce((best, o) => (Math.abs(Math.log(r / o[1])) < Math.abs(Math.log(r / best[1])) ? o : best))[0];
}

export function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
