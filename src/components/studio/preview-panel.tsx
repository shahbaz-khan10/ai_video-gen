"use client";

import { AnimatePresence, motion } from "motion/react";
import { Film, ImageIcon } from "lucide-react";
import { BackendStatusPill } from "@/components/system/backend-status";
import type { AspectRatio, GenerationMode } from "@/types/studio";
import { cn } from "@/lib/cn";
import type { CheckOutcome } from "./generation-check";
import { GeneratedImage, GenerationFooter, GenerationProgress } from "./generation-result";
import type { GenerationState } from "./generation-state";
import { OutcomeNotice } from "./outcome-notice";
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

export type GenerationControls = {
  state: GenerationState;
  onRetry: () => void;
  onResume: () => void;
  onReuseSeed: (seed: number) => void;
  onDismiss: () => void;
};

type PreviewPanelProps = {
  mode: GenerationMode;
  aspectRatio: AspectRatio;
  details: string[];
  image: SelectedImage | null;
  outcome: CheckOutcome | null;
  checking: boolean;
  onDismissOutcome: () => void;
  generation: GenerationControls;
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
  image,
  outcome,
  checking,
  onDismissOutcome,
  generation,
}: PreviewPanelProps) {
  const EmptyIcon = mode === "text-to-image" ? ImageIcon : Film;
  const showSource = mode === "image-to-video" && image;
  const isImageMode = mode === "text-to-image";
  const { state } = generation;
  const result = isImageMode && state.phase === "completed" ? state.job : null;
  // While an image is shown, the frame takes that image's shape rather than the current selection.
  const frameRatio = result ? result.settings.aspect_ratio : aspectRatio;

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
            FRAME_SIZE[frameRatio],
          )}
        >
          <div aria-hidden className="bg-grid absolute inset-0 opacity-60 [mask-image:radial-gradient(closest-side,black,transparent)]" />
          <Corners />

          <AnimatePresence mode="wait" initial={false}>
            {result ? (
              <GeneratedImage key={result.id} job={result} />
            ) : showSource ? (
              <motion.figure
                key="source"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="absolute inset-0"
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- local object URL preview */}
                <img src={image.url} alt="Source image for animation" className="size-full object-cover" />
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
                  {isImageMode
                    ? "Describe your shot and press Generate. Images are rendered by a local open-weight model."
                    : mode === "image-to-video"
                      ? "Video generation is coming soon. You can add a source image and check your settings now."
                      : "Video generation is coming soon. You can set up the shot and check your settings now."}
                </p>
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence>{isImageMode && <GenerationProgress key="progress" state={state} />}</AnimatePresence>
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

      {isImageMode ? (
        <div aria-live="polite" role="status">
          <GenerationFooter
            state={state}
            onRetry={generation.onRetry}
            onResume={generation.onResume}
            onReuseSeed={generation.onReuseSeed}
            onDismiss={generation.onDismiss}
          />
        </div>
      ) : (
        <OutcomeNotice outcome={outcome} checking={checking} onDismiss={onDismissOutcome} />
      )}
    </section>
  );
}
