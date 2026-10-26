"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { FolderOpen } from "lucide-react";
import { ASPECT_RATIOS, getMode, getStyle, isVideoMode, MODELS } from "@/lib/studio-options";
import { api } from "@/lib/api/client";
import { prefersReducedMotion } from "@/lib/motion";
import type { AspectRatio, ClipDuration, CreateDraft, GenerationMode } from "@/types/studio";
import { AspectRatioSelector } from "./aspect-ratio-selector";
import { DurationSelector } from "./duration-selector";
import { GenerateButton } from "./generate-button";
import { buildPayload, interpretError, type CheckOutcome, type FieldErrors } from "./generation-check";
import { ImageUploader } from "./image-uploader";
import { ModelSelect } from "./model-select";
import { ModeSelector } from "./mode-selector";
import { PreviewPanel } from "./preview-panel";
import { PromptEditor } from "./prompt-editor";
import { StyleSelector } from "./style-selector";
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

type CreateWorkspaceProps = {
  initial: CreateDraft;
  /** Set when the workspace was opened from a project's detail page. */
  sourceProject?: { id: string; title: string };
};

export function CreateWorkspace({ initial, sourceProject }: CreateWorkspaceProps) {
  const [mode, setMode] = useState<GenerationMode>(initial.mode);
  const [prompt, setPrompt] = useState(initial.prompt);
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>(initial.aspectRatio);
  const [style, setStyle] = useState(initial.styleId);
  const [duration, setDuration] = useState<ClipDuration>(initial.duration);
  const [model, setModel] = useState(MODELS[0].id);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [outcome, setOutcome] = useState<CheckOutcome | null>(null);
  const [checking, setChecking] = useState(false);
  // Ignores responses for a draft the user has since edited.
  const requestId = useRef(0);
  const upload = useImageSelection();

  const isVideo = isVideoMode(mode);
  const needsImage = mode === "image-to-video";

  const details = [
    getMode(mode).label,
    `${aspectRatio} ${ASPECT_RATIOS.find((r) => r.id === aspectRatio)!.label}`,
    getStyle(style).label,
    ...(isVideo ? [duration] : []),
    MODELS.find((m) => m.id === model)!.label.split(" · ")[0],
  ];

  /** Any edit makes the last check stale. */
  const invalidate = () => {
    requestId.current += 1;
    setOutcome(null);
    setChecking(false);
  };

  const changeMode = (next: GenerationMode) => {
    setMode(next);
    setErrors({});
    invalidate();
  };

  const scrollTo = (id: string, block: ScrollLogicalPosition) =>
    document.getElementById(id)?.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block });

  const revealPreviewOnSmallScreens = () => {
    // On stacked layouts the preview sits below the form; bring the result into view.
    if (window.matchMedia("(max-width: 1023px)").matches) scrollTo("preview-panel", "start");
  };

  const handleGenerate = async () => {
    // 1. Quick local checks, so obvious gaps don't need a round trip.
    const localErrors: FieldErrors = {};
    if (!prompt.trim()) localErrors.prompt = "Add a prompt to describe what you want to create.";
    if (needsImage && !upload.image) localErrors.image = "Add a source image to animate.";
    setErrors(localErrors);
    if (localErrors.image || localErrors.prompt) {
      setOutcome(null);
      scrollTo(localErrors.image ? "source-image-field" : "prompt-field", "center");
      return;
    }

    // 2. Ask the backend to validate. No model is connected, so nothing is generated either way.
    const id = ++requestId.current;
    setChecking(true);
    setOutcome(null);
    try {
      const res = await api.validateGeneration(
        buildPayload({ mode, prompt, aspectRatio, style, duration, image: upload.image }),
      );
      if (id !== requestId.current) return;
      setOutcome({ kind: "validated", settings: res.settings });
      revealPreviewOnSmallScreens();
    } catch (err) {
      if (id !== requestId.current) return;
      const { fieldErrors, outcome: next } = interpretError(err);
      setErrors(fieldErrors);
      setOutcome(next);
      if (fieldErrors.image || fieldErrors.prompt) {
        scrollTo(fieldErrors.image ? "source-image-field" : "prompt-field", "center");
      } else {
        revealPreviewOnSmallScreens();
      }
    } finally {
      if (id === requestId.current) setChecking(false);
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,400px)_minmax(0,1fr)] xl:grid-cols-[minmax(0,440px)_minmax(0,1fr)]">
      <form
        aria-label="Generation settings"
        onSubmit={(e) => e.preventDefault()}
        className="flex flex-col gap-6"
      >
        {sourceProject && (
          <p className="flex items-center gap-2 rounded-lg border border-line bg-ink-900 px-3 py-2.5 text-xs text-fg-muted">
            <FolderOpen className="size-3.5 shrink-0 text-violet-soft" aria-hidden />
            <span className="min-w-0 flex-1 truncate">
              Settings loaded from <span className="text-fg">{sourceProject.title}</span>
            </span>
            <Link
              href={`/projects/${sourceProject.id}`}
              className="shrink-0 rounded text-violet-soft hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
            >
              View project
            </Link>
          </p>
        )}

        <ModeSelector value={mode} onChange={changeMode} />

        <AnimatePresence initial={false}>
          {needsImage && (
            <motion.div key="upload" id="source-image-field" {...collapse} className="overflow-hidden">
              <ImageUploader
                image={upload.image}
                error={upload.error ?? errors.image ?? null}
                accept={upload.accept}
                onSelect={(file) => {
                  upload.select(file);
                  setErrors((e) => ({ ...e, image: undefined }));
                  invalidate();
                }}
                onClear={() => {
                  upload.clear();
                  invalidate();
                }}
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
              invalidate();
            }}
            error={errors.prompt}
          />
        </div>

        <AspectRatioSelector
          value={aspectRatio}
          onChange={(v) => {
            setAspectRatio(v);
            invalidate();
          }}
        />
        <StyleSelector
          value={style}
          onChange={(v) => {
            setStyle(v);
            invalidate();
          }}
        />

        <AnimatePresence initial={false}>
          {isVideo && (
            <motion.div key="duration" {...collapse} className="overflow-hidden">
              <DurationSelector
                value={duration}
                onChange={(v) => {
                  setDuration(v);
                  invalidate();
                }}
              />
            </motion.div>
          )}
        </AnimatePresence>

        <ModelSelect value={model} onChange={setModel} />

        <div className="sticky bottom-0 -mx-4 border-t border-line bg-ink-950/85 px-4 pb-4 pt-4 backdrop-blur-xl sm:-mx-6 sm:px-6 lg:static lg:mx-0 lg:border-0 lg:bg-transparent lg:p-0 lg:backdrop-blur-none">
          <GenerateButton onClick={handleGenerate} label={GENERATE_LABEL[mode]} busy={checking} />
        </div>
      </form>

      <div id="preview-panel" className="scroll-mt-20 lg:sticky lg:top-6 lg:self-start">
        <PreviewPanel
          mode={mode}
          aspectRatio={aspectRatio}
          details={details}
          image={upload.image}
          outcome={outcome}
          checking={checking}
          onDismissOutcome={() => setOutcome(null)}
        />
      </div>
    </div>
  );
}
