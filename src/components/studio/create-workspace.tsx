"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { FolderOpen } from "lucide-react";
import { api, assetUrl } from "@/lib/api/client";
import { useBackendStatus } from "@/lib/api/use-backend-status";
import { isBusy, parseSeed, progressMessage } from "@/lib/generation/job-view";
import { useImageJob } from "@/lib/generation/use-image-job";
import { prefersReducedMotion } from "@/lib/motion";
import { ASPECT_RATIOS, DEFAULT_IMAGE_STEPS, getMode, getStyle, IMAGE_SIZES, isVideoMode, MODELS } from "@/lib/studio-options";
import type { GenerationPayload, ImageResolution } from "@/types/api";
import type { AspectRatio, ClipDuration, CreateDraft, GenerationMode } from "@/types/studio";
import { AspectRatioSelector } from "./aspect-ratio-selector";
import { DurationSelector } from "./duration-selector";
import { GenerateButton } from "./generate-button";
import { buildPayload, interpretError, type CheckOutcome, type FieldErrors } from "./generation-check";
import { ImageModelCard } from "./image-model-card";
import { ResolutionSelector, SeedInput, StepsSelector } from "./image-options";
import { ImageUploader } from "./image-uploader";
import { JobNotice } from "./job-notice";
import { ModelSelect } from "./model-select";
import { ModeSelector } from "./mode-selector";
import { OutcomeNotice } from "./outcome-notice";
import { PreviewPanel } from "./preview-panel";
import { PromptEditor } from "./prompt-editor";
import { StyleSelector } from "./style-selector";
import { useImageSelection } from "./use-image-selection";

const GENERATE_LABEL: Record<GenerationMode, string> = {
  "text-to-image": "Generate photograph",
  "text-to-video": "Check video settings",
  "image-to-video": "Check animation settings",
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
  const [negativePrompt, setNegativePrompt] = useState("");
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>(initial.aspectRatio);
  const [style, setStyle] = useState(initial.styleId || "photorealistic");
  const [duration, setDuration] = useState<ClipDuration>(initial.duration);
  const [resolution, setResolution] = useState<ImageResolution>("standard");
  // null = the model's middle preset; the presets come from the backend once it answers.
  const [pickedSteps, setSteps] = useState<number | null>(null);
  const [seedInput, setSeedInput] = useState("");
  const [model, setModel] = useState(MODELS[0].id);
  const [errors, setErrors] = useState<FieldErrors>({});
  // Video modes: settings check only.
  const [outcome, setOutcome] = useState<CheckOutcome | null>(null);
  const [checking, setChecking] = useState(false);
  // Ignores validation responses for a draft the user has since edited.
  const requestId = useRef(0);
  const lastImagePayload = useRef<GenerationPayload | null>(null);
  const upload = useImageSelection();
  const imageJob = useImageJob();
  const { status: backend } = useBackendStatus();
  const [elapsed, setElapsed] = useState<{ jobId: string; seconds: number } | null>(null);

  const isImage = mode === "text-to-image";
  const isVideo = isVideoMode(mode);
  const needsImage = mode === "image-to-video";
  const view = imageJob.view;
  const imageBusy = isBusy(view);
  const viewJob = "job" in view ? view.job : null;

  // Wall-clock timer while the server reports "processing"; ticks only from the interval.
  useEffect(() => {
    if (view.phase !== "processing" || !view.job.started_at) return;
    const { id, started_at } = view.job;
    const started = Date.parse(started_at);
    const timer = setInterval(() => setElapsed({ jobId: id, seconds: (Date.now() - started) / 1000 }), 1000);
    return () => clearInterval(timer);
  }, [view]);

  const elapsedSeconds = viewJob && elapsed?.jobId === viewJob.id ? elapsed.seconds : 0;
  const license = backend.state === "online" ? backend.info.generation.license : null;
  const size = (IMAGE_SIZES[resolution] || IMAGE_SIZES.standard)[aspectRatio];
  const stepOptions =
    backend.state === "online" && backend.info.limits.image_steps.length > 0
      ? backend.info.limits.image_steps
      : DEFAULT_IMAGE_STEPS;
  const steps =
    pickedSteps !== null && stepOptions.includes(pickedSteps)
      ? pickedSteps
      : stepOptions[Math.floor((stepOptions.length - 1) / 2)];

  const details = isImage
    ? [
        getMode(mode).label,
        `${aspectRatio} · ${size.width}×${size.height}`,
        getStyle(style).label,
        `${steps} steps`,
        seedInput.trim() ? `Seed ${seedInput.trim()}` : "Random seed",
      ]
    : [
        getMode(mode).label,
        `${aspectRatio} ${ASPECT_RATIOS.find((r) => r.id === aspectRatio)!.label}`,
        getStyle(style).label,
        duration,
        MODELS.find((m) => m.id === model)!.label.split(" · ")[0],
      ];

  /** Any edit makes the last settings check stale. A running image job keeps going. */
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
    if (window.matchMedia("(max-width: 1023px)").matches) scrollTo("preview-panel", "start");
  };

  const submitImage = (payload: GenerationPayload) => {
    lastImagePayload.current = payload;
    void imageJob.submit(payload);
    revealPreviewOnSmallScreens();
  };

  const handleGenerate = async () => {
    const localErrors: FieldErrors = {};
    if (!prompt.trim()) localErrors.prompt = "Add a prompt to describe what you want to create.";
    if (needsImage && !upload.image) localErrors.image = "Add a source image to animate.";
    const seed = parseSeed(seedInput);
    if (isImage && seed.error) localErrors.seed = seed.error;
    setErrors(localErrors);
    if (localErrors.image || localErrors.prompt || localErrors.seed) {
      setOutcome(null);
      scrollTo(localErrors.image ? "source-image-field" : localErrors.prompt ? "prompt-field" : "seed-field", "center");
      return;
    }

    const payload = buildPayload({
      mode,
      prompt,
      negativePrompt,
      aspectRatio,
      style,
      duration,
      image: upload.image,
      resolution,
      steps,
      seed: seed.seed,
      // Image jobs run on the backend's configured model (shown in the model card); only video has a picker.
      modelId: isImage ? undefined : model,
    });

    if (isImage) {
      submitImage(payload);
      return;
    }

    const id = ++requestId.current;
    setChecking(true);
    setOutcome(null);
    try {
      const res = await api.validateGeneration(payload);
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

  const completedImage = isImage && view.phase === "completed" ? view.job.image : null;
  const resultSrc = completedImage ? assetUrl(completedImage.url) : null;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,400px)_minmax(0,1fr)] xl:grid-cols-[minmax(0,440px)_minmax(0,1fr)]">
      <form aria-label="Generation settings" onSubmit={(e) => e.preventDefault()} className="flex flex-col gap-6">
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
            negativePrompt={negativePrompt}
            onNegativePromptChange={setNegativePrompt}
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

        <AnimatePresence initial={false} mode="popLayout">
          {isImage ? (
            <motion.div key="image-options" {...collapse} className="flex flex-col gap-6 overflow-hidden">
              <ResolutionSelector value={resolution} aspectRatio={aspectRatio} onChange={setResolution} />
              <StepsSelector options={stepOptions} value={steps} onChange={setSteps} />
              <div id="seed-field">
                <SeedInput
                  value={seedInput}
                  onChange={(v) => {
                    setSeedInput(v);
                    setErrors((e) => ({ ...e, seed: undefined }));
                  }}
                  error={errors.seed}
                />
              </div>
              <ImageModelCard refreshKey={viewJob ? `${viewJob.id}:${view.phase}` : view.phase} />
            </motion.div>
          ) : (
            <motion.div key="video-options" {...collapse} className="flex flex-col gap-6 overflow-hidden">
              {isVideo && (
                <DurationSelector
                  value={duration}
                  onChange={(v) => {
                    setDuration(v);
                    invalidate();
                  }}
                />
              )}
              <ModelSelect value={model} onChange={setModel} />
            </motion.div>
          )}
        </AnimatePresence>

        <div className="sticky bottom-0 -mx-4 border-t border-line bg-ink-950/85 px-4 pb-4 pt-4 backdrop-blur-xl sm:-mx-6 sm:px-6 lg:static lg:mx-0 lg:border-0 lg:bg-transparent lg:p-0 lg:backdrop-blur-none">
          <GenerateButton
            onClick={handleGenerate}
            label={GENERATE_LABEL[mode]}
            busy={isImage ? imageBusy : checking}
            busyLabel={isImage ? "Generating photograph…" : "Checking settings…"}
            note={
              isImage
                ? "Photorealistic engine · Scene understanding and anatomical preservation active"
                : "Video generation is coming soon · settings are validated only"
            }
          />
        </div>
      </form>

      <div id="preview-panel" className="scroll-mt-20 lg:sticky lg:top-6 lg:self-start">
        <PreviewPanel
          mode={mode}
          aspectRatio={completedImage && viewJob ? viewJob.settings.aspect_ratio : aspectRatio}
          details={details}
          sourceImage={upload.image}
          result={resultSrc ? { src: resultSrc, alt: `Generated image: ${viewJob?.settings.prompt ?? ""}` } : null}
          busyMessage={isImage && imageBusy ? progressMessage(view, elapsedSeconds, imageJob.modelState) : null}
          notice={
            isImage ? (
              <JobNotice
                view={view}
                progress={progressMessage(view, elapsedSeconds, imageJob.modelState)}
                attribution={license ? { text: license.attribution, url: license.url } : null}
                onRetry={() => lastImagePayload.current && submitImage(lastImagePayload.current)}
                onReconnect={imageJob.reconnect}
              />
            ) : (
              <OutcomeNotice outcome={outcome} checking={checking} onDismiss={() => setOutcome(null)} />
            )
          }
        />
      </div>
    </div>
  );
}
