"use client";

import type { ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Film, ImageIcon, LoaderCircle } from "lucide-react";
import { BackendStatusPill } from "@/components/system/backend-status";
import type { AspectRatio, GenerationMode } from "@/types/studio";
import { cn } from "@/lib/cn";
import type { SelectedImage } from "./use-image-selection";

const RESULT_NOUN: Record<GenerationMode, string> = {
  "text-to-image": "image",
  "text-to-video": "video",
  "image-to-video": "animation",
};

const FRAME_SIZE: Record<AspectRatio, string> = {
  "16:9": "aspect-video w-full",
  "9:16": "aspect-[9/16] w-full max-w-[250px] lg:max-w-[300px]",
  "1:1": "aspect-square w-full max-w-[360px] lg:max-w-[480px]",
};

type PreviewPanelProps = {
  mode: GenerationMode;
  /** Shape of the frame. A finished result keeps its own ratio even if the selector changes. */
  aspectRatio: AspectRatio;
  details: string[];
  sourceImage: SelectedImage | null;
  /** A real generated image from the backend. */
  result: { src: string; alt: string } | null;
  /** Shown over the frame while a job is in progress. */
  busyMessage: string | null;
  /** Status, errors and actions below the preview. */
  notice: ReactNode;
};

function Corners() {
  const base = "absolute size-4 border-white/25";
  return (
    <span aria-hidden>
      <span className={cn(base, "left-3 top-3 border-l border-t")} />
      <span className={cn(base, "right-3 top-3 border-r border-t")} />
      <span className={cn(base, "bottom-3 left-3 border-b border-l")} />
      <span className={cn(base, "bottom-3 right-3 border-b border-r")} />
    </span>
  );
}

export function PreviewPanel({
  mode,
  aspectRatio,
  details,
  sourceImage,
  result,
  busyMessage,
  notice,
}: PreviewPanelProps) {
  const EmptyIcon = mode === "text-to-image" ? ImageIcon : Film;
  const showSource = mode === "image-to-video" && sourceImage;

  return (
    <section aria-labelledby="preview-heading" className="flex flex-col rounded-2xl border border-line bg-ink-900/60">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 id="preview-heading" className="text-[13px] font-medium text-fg">
          Preview
        </h2>
        <BackendStatusPill />
      </div>

      <div className="grid min-h-[380px] flex-1 place-items-center bg-[radial-gradient(70%_60%_at_50%_45%,rgb(99_102_241/0.07),transparent)] p-4 sm:p-6 lg:min-h-[600px]">
        <motion.div
          layout
          transition={{ type: "spring", stiffness: 260, damping: 32 }}
          className={cn(
            "relative max-h-full overflow-hidden rounded-xl border border-line-strong bg-ink-950",
            FRAME_SIZE[aspectRatio],
          )}
        >
          <div aria-hidden className="bg-grid absolute inset-0 opacity-60 [mask-image:radial-gradient(closest-side,black,transparent)]" />
          <Corners />

          <AnimatePresence mode="wait" initial={false}>
            {result ? (
              <motion.figure
                key={result.src}
                initial={{ opacity: 0, scale: 1.02 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.45 }}
                className="absolute inset-0"
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- image served by our own API */}
                <img src={result.src} alt={result.alt} className="size-full object-cover" />
              </motion.figure>
            ) : showSource ? (
              <motion.figure
                key="source"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="absolute inset-0"
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- local object URL preview */}
                <img src={sourceImage.url} alt="Source image for animation" className="size-full object-cover" />
                <figcaption className="absolute left-3 top-3 rounded-md bg-black/50 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-white/85 backdrop-blur">
                  Source frame · not animated
                </figcaption>
              </motion.figure>
            ) : (
              <motion.div
                key={mode}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.25 }}
                className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center"
              >
                <span className="grid size-12 place-items-center rounded-full border border-line-strong bg-ink-850 text-violet-soft">
                  <EmptyIcon className="size-5" aria-hidden />
                </span>
                <p className="mt-4 text-sm font-medium text-fg">Your {RESULT_NOUN[mode]} will appear here</p>
                <p className="mt-1.5 max-w-xs text-xs leading-relaxed text-fg-muted">
                  {mode === "text-to-image"
                    ? "Describe your shot and press Generate. The image renders here on your local model."
                    : "Video generation is coming soon. You can set up the shot and check its settings."}
                </p>
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence>
            {busyMessage && (
              <motion.div
                key="busy"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-ink-950/75 p-6 text-center backdrop-blur-sm"
              >
                <span aria-hidden className="absolute inset-0 overflow-hidden">
                  <span className="animate-scan absolute inset-y-0 left-0 w-1/3 bg-linear-to-r from-transparent via-violet/15 to-transparent" />
                </span>
                <LoaderCircle className="relative size-6 animate-spin text-violet-soft" aria-hidden />
                <p className="relative max-w-xs text-sm text-fg">{busyMessage}</p>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </div>

      <div className="border-t border-line px-4 py-3">
        <ul aria-label="Current settings" className="flex flex-wrap gap-1.5">
          {details.map((d) => (
            <li key={d} className="rounded-md border border-line bg-ink-850 px-2 py-1 text-[11px] text-fg-muted">
              {d}
            </li>
          ))}
        </ul>
      </div>

      {notice}
    </section>
  );
}
