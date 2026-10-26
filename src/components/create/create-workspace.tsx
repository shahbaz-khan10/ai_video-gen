"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  ASPECT_RATIOS,
  EXAMPLE_PROMPT,
  MODELS,
  MODES,
  VISUAL_STYLES,
  type AspectRatio,
  type GenerationMode,
} from "@/lib/studio-options";
import { GenerateButton } from "./generate-button";
import { ImageUpload } from "./image-upload";
import { ModeSelector } from "./mode-selector";
import { PreviewPanel } from "./preview-panel";
import { PromptEditor } from "./prompt-editor";
import { AspectRatioSelector, DurationSelector, ModelSelect, StyleSelector, type Duration } from "./setting-controls";
import { useImageSelection } from "./use-image-selection";

const GENERATE_LABEL: Record<GenerationMode, string> = {
  "text-to-image": "Generate image",
  "text-to-video": "Generate video",
  "image-to-video": "Animate image",
};

const collapse = {
  initial: { opacity: 0, height: 0 },
  animate: { opacity: 1, height: "auto" },
  exit: { opacity: 0, height: 0 },
  transition: { duration: 0.28, ease: [0.22, 1, 0.36, 1] as const },
};

export function CreateWorkspace({ initialMode = "text-to-video" }: { initialMode?: GenerationMode }) {
  const [mode, setMode] = useState<GenerationMode>(initialMode);
  const [prompt, setPrompt] = useState(EXAMPLE_PROMPT);
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>("16:9");
  const [style, setStyle] = useState(VISUAL_STYLES[0].id);
  const [duration, setDuration] = useState<Duration>("6s");
  const [model, setModel] = useState(MODELS[0].id);
  const [errors, setErrors] = useState<{ prompt?: string; image?: string }>({});
  const [showNotice, setShowNotice] = useState(false);
  const upload = useImageSelection();

  const isVideo = mode !== "text-to-image";
  const needsImage = mode === "image-to-video";

  const details = [
    MODES.find((m) => m.id === mode)!.label,
    `${aspectRatio} ${ASPECT_RATIOS.find((r) => r.id === aspectRatio)!.label}`,
    VISUAL_STYLES.find((s) => s.id === style)!.label,
    ...(isVideo ? [duration] : []),
    MODELS.find((m) => m.id === model)!.label.split(" · ")[0],
  ];

  const changeMode = (next: GenerationMode) => {
    setMode(next);
    setErrors({});
    setShowNotice(false);
  };

  const handleGenerate = () => {
    const nextErrors: typeof errors = {};
    if (!prompt.trim()) nextErrors.prompt = "Add a prompt to describe what you want to create.";
    if (needsImage && !upload.image) nextErrors.image = "Add a source image to animate.";
    setErrors(nextErrors);
    // Phase 1: never pretend to generate. Only explain that no model is connected.
    const valid = Object.keys(nextErrors).length === 0;
    setShowNotice(valid);

    const firstInvalid = nextErrors.image ? "source-image-field" : nextErrors.prompt ? "prompt-field" : null;
    if (firstInvalid) {
      document.getElementById(firstInvalid)?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }

    // On stacked layouts the preview sits below the form; bring the notice into view.
    if (valid && window.matchMedia("(max-width: 1023px)").matches) {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      document.getElementById("preview-panel")?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,400px)_minmax(0,1fr)] xl:grid-cols-[minmax(0,440px)_minmax(0,1fr)]">
      <form
        aria-label="Generation settings"
        onSubmit={(e) => e.preventDefault()}
        className="flex flex-col gap-6"
      >
        <ModeSelector value={mode} onChange={changeMode} />

        <AnimatePresence initial={false}>
          {needsImage && (
            <motion.div key="upload" id="source-image-field" {...collapse} className="overflow-hidden">
              <ImageUpload
                image={upload.image}
                error={upload.error ?? errors.image ?? null}
                accept={upload.accept}
                onSelect={(file) => {
                  upload.select(file);
                  setErrors((e) => ({ ...e, image: undefined }));
                }}
                onClear={upload.clear}
              />
            </motion.div>
          )}
        </AnimatePresence>

        <div id="prompt-field">
          <PromptEditor
            mode={mode}
            value={prompt}
            onChange={(value) => {
              setPrompt(value);
              if (value.trim()) setErrors((e) => ({ ...e, prompt: undefined }));
              setShowNotice(false);
            }}
            error={errors.prompt}
          />
        </div>

        <AspectRatioSelector value={aspectRatio} onChange={setAspectRatio} />
        <StyleSelector value={style} onChange={setStyle} />

        <AnimatePresence initial={false}>
          {isVideo && (
            <motion.div key="duration" {...collapse} className="overflow-hidden">
              <DurationSelector value={duration} onChange={setDuration} />
            </motion.div>
          )}
        </AnimatePresence>

        <ModelSelect value={model} onChange={setModel} />

        <div className="sticky bottom-0 -mx-4 border-t border-line bg-ink-950/85 px-4 pb-4 pt-4 backdrop-blur-xl sm:-mx-6 sm:px-6 lg:static lg:mx-0 lg:border-0 lg:bg-transparent lg:p-0 lg:backdrop-blur-none">
          <GenerateButton onClick={handleGenerate} label={GENERATE_LABEL[mode]} />
        </div>
      </form>

      <div id="preview-panel" className="scroll-mt-20 lg:sticky lg:top-6 lg:self-start">
        <PreviewPanel
          mode={mode}
          aspectRatio={aspectRatio}
          details={details}
          image={upload.image}
          showNotice={showNotice}
          onDismissNotice={() => setShowNotice(false)}
        />
      </div>
    </div>
  );
}
