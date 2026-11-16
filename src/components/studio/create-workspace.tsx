"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { FolderOpen, ScanSearch, Square } from "lucide-react";
import { api, ApiError, assetUrl } from "@/lib/api/client";
import { useBackendStatus } from "@/lib/api/use-backend-status";
import { isBusy, parseSeed, progressMessage } from "@/lib/generation/job-view";
import { useImageJob } from "@/lib/generation/use-image-job";
import { prefersReducedMotion } from "@/lib/motion";
import {
  DEFAULT_IMAGE_STEPS,
  DEFAULT_VIDEO_DURATIONS,
  DEFAULT_VIDEO_STEPS,
  getMode,
  estimateI2VSeconds,
  getStyle,
  I2V_DURATIONS,
  IMAGE_SIZES,
  isVideoMode,
  MODELS,
  VIDEO_SIZES,
} from "@/lib/studio-options";
import type {
  GenerationPayload,
  GenerationPlan,
  I2VCamera,
  I2VMotion,
  I2VQuality,
  ImageResolution,
  SceneInput,
  VideoResolution,
} from "@/types/api";
import type { AspectRatio, ClipDuration, CreateDraft, GenerationMode } from "@/types/studio";
import { AspectRatioSelector } from "./aspect-ratio-selector";
import { DurationSelector } from "./duration-selector";
import { AgentReport } from "./agent-report";
import { TalkingPanel } from "./talking-panel";
import { GenerateButton } from "./generate-button";
import { formatEstimate, I2VCameraSelector, I2VDurationSelector, I2VMotionSelector, I2VQualitySelector } from "./i2v-options";
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
import { ScenePlanPanel } from "./scene-plan-panel";
import { SceneProgress } from "./scene-progress";
import { StyleSelector } from "./style-selector";
import { nearestAspect, useImageSelection } from "./use-image-selection";
import { VideoDurationSelector, VideoSizeSelector } from "./video-options";

const GENERATE_LABEL: Record<GenerationMode, string> = {
  "text-to-image": "Generate photograph",
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
  const [negativePrompt, setNegativePrompt] = useState("");
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>(initial.aspectRatio);
  const [style, setStyle] = useState(initial.styleId || "photorealistic");
  const [duration, setDuration] = useState<ClipDuration>(initial.duration);
  const [resolution, setResolution] = useState<ImageResolution>("standard");
  // null = the model's middle preset; the presets come from the backend once it answers.
  const [pickedSteps, setSteps] = useState<number | null>(null);
  const [seedInput, setSeedInput] = useState("");
  // Text-to-video settings; null = the model's default, known once /info answers.
  const [pickedVideoSeconds, setVideoSeconds] = useState<number | null>(null);
  const [videoResolution, setVideoResolution] = useState<VideoResolution>("standard");
  const [pickedVideoSteps, setVideoSteps] = useState<number | null>(null);
  const [model, setModel] = useState(MODELS[0].id);
  // Image-to-video settings.
  const [i2vQuality, setI2vQuality] = useState<I2VQuality>("draft");
  const [i2vSeconds, setI2vSeconds] = useState(3);
  const [i2vMotion, setI2vMotion] = useState<I2VMotion>("normal");
  const [i2vCamera, setI2vCamera] = useState<I2VCamera>("none");
  const [i2vResolution, setI2vResolution] = useState<VideoResolution>("standard");
  // 480p was measured in Draft only; Quality at 480p is not offered.
  const i2vSize: VideoResolution = i2vQuality === "draft" ? i2vResolution : "standard";
  const [cancelling, setCancelling] = useState(false);
  const [promptAgent, setPromptAgent] = useState(true);
  // Job IDs the user asked to stop; the server stops at the next step (after a model load if one is running).
  const [stopRequested, setStopRequested] = useState<string | null>(null);
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
  // How the backend understood the current draft (Plan scenes); cleared on any edit that changes it.
  const [plan, setPlan] = useState<GenerationPlan | null>(null);
  const [planScenes, setPlanScenes] = useState<SceneInput[] | null>(null);
  const [planning, setPlanning] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const planRequest = useRef(0);
  const [elapsed, setElapsed] = useState<{ jobId: string; seconds: number } | null>(null);

  const isImage = mode === "text-to-image";
  const isTextToVideo = mode === "text-to-video";
  const isI2V = mode === "image-to-video";
  // Modes that queue a real job on a local model (all three).
  const runsJob = isImage || isTextToVideo || isI2V;
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

  // A new picture picks the closest aspect ratio, so it is cropped as little as possible. The user can change it.
  const pickedFor = useRef<string | null>(null);
  useEffect(() => {
    const img = upload.image;
    if (!img || pickedFor.current === img.url) return;
    pickedFor.current = img.url;
    setAspectRatio(nearestAspect(img.width, img.height));
  }, [upload.image]);

  const elapsedSeconds = viewJob && elapsed?.jobId === viewJob.id ? elapsed.seconds : 0;
  const license =
    backend.state === "online"
      ? mode !== "text-to-image"
        ? backend.info.video?.license ?? null
        : backend.info.generation.license
      : null;
  const size = (IMAGE_SIZES[resolution] || IMAGE_SIZES.standard)[aspectRatio];
  const stepOptions =
    backend.state === "online" && backend.info.limits.image_steps.length > 0
      ? backend.info.limits.image_steps
      : DEFAULT_IMAGE_STEPS;
  const steps =
    pickedSteps !== null && stepOptions.includes(pickedSteps)
      ? pickedSteps
      : stepOptions[Math.floor((stepOptions.length - 1) / 2)];

  const online = backend.state === "online" ? backend : null;
  const videoInfo = online?.info.video ?? null;
  const videoFps = online?.info.limits.video_fps ?? 16;
  const videoDurations = online?.info.limits.video_duration_options_seconds?.length
    ? online.info.limits.video_duration_options_seconds
    : DEFAULT_VIDEO_DURATIONS;
  const videoStepOptions = online?.info.limits.video_steps?.length ? online.info.limits.video_steps : DEFAULT_VIDEO_STEPS;
  const videoSeconds =
    pickedVideoSeconds !== null && videoDurations.includes(pickedVideoSeconds) ? pickedVideoSeconds : videoDurations[0];
  const videoSteps =
    pickedVideoSteps !== null && videoStepOptions.includes(pickedVideoSteps)
      ? pickedVideoSteps
      : videoStepOptions[Math.floor((videoStepOptions.length - 1) / 2)];
  const videoSize = VIDEO_SIZES[videoResolution][aspectRatio];
  // FastWan runs a fixed 3-step schedule; the API rejects a steps value then.
  const fixedVideoSteps = online?.info.limits.video_sampler === "fastwan";
  // Up to 5 s is one clip; longer videos are planned as scenes.
  const isLongVideo = isTextToVideo && videoSeconds > 5;

  const details = isTextToVideo
    ? [
        getMode(mode).label,
        `${aspectRatio} · ${videoSize.width}×${videoSize.height}`,
        getStyle(style).label,
        `${videoSeconds}s @ ${videoFps} fps`,
        fixedVideoSteps ? "FastWan · 3 steps" : `${videoSteps} steps`,
        ...(isLongVideo && planScenes ? [`${planScenes.length} scenes`] : []),
        seedInput.trim() ? `Seed ${seedInput.trim()}` : "Random seed",
      ]
    : isImage
    ? [
        getMode(mode).label,
        `${aspectRatio} · ${size.width}×${size.height}`,
        getStyle(style).label,
        `${steps} steps`,
        seedInput.trim() ? `Seed ${seedInput.trim()}` : "Random seed",
      ]
    : [
        getMode(mode).label,
        `${aspectRatio} · ${VIDEO_SIZES[i2vSize][aspectRatio].width}×${VIDEO_SIZES[i2vSize][aspectRatio].height}`,
        `${i2vSeconds}s @ ${videoFps} fps`,
        i2vQuality === "draft" ? "Draft · 3 steps" : "Quality · 20 steps",
        seedInput.trim() ? `Seed ${seedInput.trim()}` : "Random seed",
      ];

  /** Any edit makes the last settings check stale. A running image job keeps going. */
  const invalidate = () => {
    requestId.current += 1;
    setOutcome(null);
    setChecking(false);
    clearPlan();
  };

  function clearPlan() {
    planRequest.current += 1;
    setPlan(null);
    setPlanScenes(null);
    setPlanning(false);
    setPlanError(null);
  }

  const changeVideoSeconds = (value: number) => {
    setVideoSeconds(value);
    clearPlan();
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

  const draftPayload = (seed: number | null, scenes?: SceneInput[]) =>
    buildPayload({
      mode,
      prompt,
      negativePrompt,
      aspectRatio,
      style,
      duration,
      image: upload.image,
      resolution,
      steps,
      seed,
      // Image and text-to-video jobs run on the backend's configured models; no client-side model switch.
      modelId: runsJob ? undefined : model,
      video: {
        durationSeconds: videoSeconds,
        resolution: videoResolution,
        steps: fixedVideoSteps ? null : videoSteps,
        scenes,
      },
      promptAgent,
      i2v: { durationSeconds: i2vSeconds, resolution: i2vSize, quality: i2vQuality, motion: i2vMotion, camera: i2vCamera },
    });

  /** Asks the backend how it understood the prompt; long videos also get an editable scene list. */
  const handlePlan = async () => {
    if (!prompt.trim()) {
      setErrors((e) => ({ ...e, prompt: "Add a prompt to describe what you want to create." }));
      scrollTo("prompt-field", "center");
      return;
    }
    const id = ++planRequest.current;
    setPlanning(true);
    setPlanError(null);
    try {
      const result = await api.scenePlan(draftPayload(null));
      if (id !== planRequest.current) return;
      setPlan(result);
      setPlanScenes(
        isLongVideo
          ? result.scenes.map((s) => ({ description: s.description, duration_seconds: s.duration_seconds ?? undefined }))
          : null,
      );
    } catch (err) {
      if (id !== planRequest.current) return;
      setPlanError(err instanceof ApiError ? err.message : "Couldn't plan the scenes.");
    } finally {
      if (id === planRequest.current) setPlanning(false);
    }
  };

  const handleRetryScene = async (index: number) => {
    if (!viewJob) return;
    try {
      imageJob.adopt(await api.retryScene(viewJob.id, index));
    } catch (err) {
      setPlanError(err instanceof ApiError ? err.message : "Couldn't retry the scene.");
    }
  };

  const handleGenerate = async () => {
    const localErrors: FieldErrors = {};
    if (!prompt.trim()) localErrors.prompt = "Add a prompt to describe what you want to create.";
    if (needsImage && !upload.image) localErrors.image = "Add a source image to animate.";
    else if (needsImage && upload.image?.uploading) localErrors.image = "The image is still uploading. Try again in a moment.";
    else if (needsImage && !upload.image?.uploadId) localErrors.image = "The image was not uploaded. Use “Upload again”.";
    const seed = parseSeed(seedInput);
    if (runsJob && seed.error) localErrors.seed = seed.error;
    setErrors(localErrors);
    if (localErrors.image || localErrors.prompt || localErrors.seed) {
      setOutcome(null);
      scrollTo(localErrors.image ? "source-image-field" : localErrors.prompt ? "prompt-field" : "seed-field", "center");
      return;
    }

    const scenes = isLongVideo && planScenes ? planScenes.filter((s) => s.description.trim()) : undefined;
    const payload = draftPayload(seed.seed, scenes);

    if (runsJob) {
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

  // A finished job is only shown in the mode that produced it.
  const completedJob = view.phase === "completed" && view.job.settings.mode === mode ? view.job : null;
  const completedImage = isImage ? completedJob?.image ?? null : null;
  const completedVideo = isTextToVideo || isI2V ? completedJob?.video ?? null : null;

  const handleCancel = async () => {
    if (!viewJob) return;
    setCancelling(true);
    try {
      setStopRequested(viewJob.id);
      imageJob.adopt(await api.cancelGeneration(viewJob.id));
    } catch (err) {
      setPlanError(err instanceof ApiError ? err.message : "Couldn't cancel the job.");
    } finally {
      setCancelling(false);
    }
  };
  const resultSrc = completedImage ? assetUrl(completedImage.url) : completedVideo ? assetUrl(completedVideo.url) : null;
  const jobInThisMode = viewJob === null || viewJob.settings.mode === mode;
  const jobBusy = imageBusy && jobInThisMode;
  const canCancel = jobBusy && viewJob !== null && viewJob.settings.mode !== "text-to-image" && !cancelling;

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
                onRetryUpload={upload.retryUpload}
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
        {/* Style words would repaint the uploaded picture, so image-to-video has no style. */}
        {!isI2V && (
          <StyleSelector
            value={style}
            onChange={(v) => {
              setStyle(v);
              invalidate();
            }}
          />
        )}

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
          ) : isTextToVideo ? (
            <motion.div key="text-to-video-options" {...collapse} className="flex flex-col gap-6 overflow-hidden">
              <VideoDurationSelector
                options={videoDurations}
                fps={videoFps}
                value={videoSeconds}
                onChange={changeVideoSeconds}
              />
              <VideoSizeSelector value={videoResolution} aspectRatio={aspectRatio} onChange={setVideoResolution} />
              {!fixedVideoSteps && <StepsSelector options={videoStepOptions} value={videoSteps} onChange={setVideoSteps} />}
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
              <p className="rounded-lg border border-line bg-ink-900 px-3 py-2.5 text-xs leading-relaxed text-fg-muted">
                <span className="font-mono text-fg">{videoInfo?.model_id ?? "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"}</span>
                {" · "}
                {videoInfo ? (videoInfo.available ? videoInfo.message : videoInfo.detail) : "Checking the video model…"}
              </p>
            </motion.div>
          ) : isI2V ? (
            <motion.div key="i2v-options" {...collapse} className="flex flex-col gap-6 overflow-hidden">
              <I2VQualitySelector value={i2vQuality} onChange={setI2vQuality} seconds={i2vSeconds} resolution={i2vSize} />
              {i2vQuality === "draft" && (
                <VideoSizeSelector
                  value={i2vResolution}
                  aspectRatio={aspectRatio}
                  onChange={setI2vResolution}
                  labels={{ standard: "Small", large: "480p" }}
                  hint="Small (~320p) is quickest. 480p is sharper and keeps more of the photo's detail, but takes about 3x as long."
                />
              )}
              <I2VDurationSelector
                options={online?.info.limits.duration_options_seconds?.length ? online.info.limits.duration_options_seconds : I2V_DURATIONS}
                value={i2vSeconds}
                onChange={setI2vSeconds}
              />
              <I2VMotionSelector value={i2vMotion} onChange={setI2vMotion} />
              <I2VCameraSelector value={i2vCamera} onChange={setI2vCamera} />
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
              <p className="rounded-lg border border-line bg-ink-900 px-3 py-2.5 text-xs leading-relaxed text-fg-muted">
                <span className="font-mono text-fg">Wan-AI/Wan2.1-VACE-1.3B-diffusers</span> · Apache-2.0 · the uploaded image is
                the first frame and is centre-cropped to {aspectRatio} ({VIDEO_SIZES[i2vSize][aspectRatio].width}×
                {VIDEO_SIZES[i2vSize][aspectRatio].height}). Faces can drift a little; large or fast movements are weak.
              </p>
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

        {(isImage || isTextToVideo) && (
          <div className="flex flex-col gap-3">
            <button
              type="button"
              onClick={handlePlan}
              disabled={planning}
              className="flex items-center justify-center gap-2 rounded-lg border border-line bg-ink-900 px-3 py-2.5 text-xs font-medium text-fg-muted hover:border-violet-soft/40 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/40 disabled:opacity-60"
            >
              <ScanSearch className="size-3.5" aria-hidden />
              {planning ? "Reading your prompt…" : isLongVideo ? "Plan scenes" : "Check how the prompt is understood"}
            </button>
            {planError && (
              <p role="alert" className="text-xs text-red-300">
                {planError}
              </p>
            )}
            {plan && (
              <ScenePlanPanel
                plan={plan}
                scenes={isLongVideo ? planScenes : null}
                totalSeconds={isLongVideo ? videoSeconds : null}
                onScenesChange={setPlanScenes}
              />
            )}
          </div>
        )}

        {runsJob && (
          <label className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-line bg-ink-900 px-3 py-2.5 text-xs text-fg-muted">
            <input
              type="checkbox"
              checked={promptAgent}
              onChange={(e) => setPromptAgent(e.target.checked)}
              className="mt-0.5 accent-violet-500"
            />
            <span>
              <span className="font-medium text-fg">Prompt agent</span> · looks at the picture with Florence-2: describes an
              uploaded photo for the prompt, checks counts and background in the result, and tries once more with another
              seed if a check fails. Adds a few seconds; a retry adds a full generation.
            </span>
          </label>
        )}

        <div className="sticky bottom-0 -mx-4 border-t border-line bg-ink-950/85 px-4 pb-4 pt-4 backdrop-blur-xl sm:-mx-6 sm:px-6 lg:static lg:mx-0 lg:border-0 lg:bg-transparent lg:p-0 lg:backdrop-blur-none">
          <GenerateButton
            onClick={handleGenerate}
            label={GENERATE_LABEL[mode]}
            busy={runsJob ? jobBusy || (imageBusy && !jobInThisMode) : checking}
            busyLabel={
              runsJob && !jobInThisMode
                ? "Another job is running…"
                : isImage
                ? "Generating photograph…"
                : isTextToVideo
                ? "Generating video…"
                : isI2V
                ? "Animating image…"
                : "Checking settings…"
            }
            note={
              isImage
                ? "Photorealistic engine · Scene understanding and anatomical preservation active"
                : isTextToVideo
                ? isLongVideo
                  ? `Runs on your GPU · ${videoSeconds}s is built from many clips and takes a long time · one job at a time`
                  : "Runs on your GPU · about a minute or more per clip · one job at a time"
                : `Runs on your GPU · about ${formatEstimate(estimateI2VSeconds(i2vQuality, i2vSize, i2vSeconds))} (plus ~1 min the first time the model loads) · one job at a time`
            }
          />
        </div>
      </form>

      <div id="preview-panel" className="scroll-mt-20 lg:sticky lg:top-6 lg:self-start">
        <PreviewPanel
          mode={mode}
          aspectRatio={completedJob ? completedJob.settings.aspect_ratio : aspectRatio}
          details={details}
          sourceImage={upload.image}
          result={
            resultSrc
              ? {
                  kind: completedVideo ? "video" : "image",
                  src: resultSrc,
                  alt: `Generated ${completedVideo ? "video" : "image"}: ${completedJob?.settings.prompt ?? ""}`,
                }
              : null
          }
          busyMessage={runsJob && jobBusy ? progressMessage(view, elapsedSeconds, imageJob.modelState) : null}
          notice={
            runsJob && jobInThisMode ? (
              <>
                {jobBusy && viewJob && stopRequested === viewJob.id && (
                  <p role="status" className="mb-3 text-xs text-fg-muted">
                    Stopping… the job stops at its next step. If the model is still loading, that finishes first.
                  </p>
                )}
                {canCancel && stopRequested !== viewJob?.id && (
                  <button
                    type="button"
                    onClick={() => void handleCancel()}
                    className="mb-3 flex items-center gap-1.5 rounded-lg border border-line bg-ink-900 px-3 py-2 text-xs font-medium text-fg-muted hover:border-red-400/40 hover:text-red-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/40"
                  >
                    <Square className="size-3" aria-hidden />
                    Cancel generation
                  </button>
                )}
                <JobNotice
                  view={view}
                  progress={progressMessage(view, elapsedSeconds, imageJob.modelState)}
                  attribution={license ? { text: license.attribution, url: license.url } : null}
                  onRetry={() => lastImagePayload.current && submitImage(lastImagePayload.current)}
                  onReconnect={imageJob.reconnect}
                />
                {viewJob?.agent && <AgentReport agent={viewJob.agent} />}
                {completedVideo && completedJob && !completedJob.scenes?.length && (
                  <TalkingPanel sourceJobId={completedJob.id} />
                )}
                {viewJob?.scenes && viewJob.scenes.length > 0 && (
                  <SceneProgress
                    scenes={viewJob.scenes}
                    canRetry={view.phase === "failed"}
                    onRetry={(index) => void handleRetryScene(index)}
                  />
                )}
              </>
            ) : (
              <OutcomeNotice outcome={outcome} checking={checking} onDismiss={() => setOutcome(null)} />
            )
          }
        />
      </div>
    </div>
  );
}
