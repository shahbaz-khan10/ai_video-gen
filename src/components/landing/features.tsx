import { ArrowRight, Type } from "lucide-react";
import { Reveal } from "@/components/motion/reveal";
import { Poster } from "@/components/ui/poster";
import { SectionLabel } from "@/components/ui/section-label";
import { MODES, type GenerationMode } from "@/lib/studio-options";

const DETAILS: Record<GenerationMode, { headline: string; points: string[] }> = {
  "text-to-image": {
    headline: "Compose a frame in words.",
    points: ["Style presets tuned for film looks", "Landscape, portrait and square framing"],
  },
  "text-to-video": {
    headline: "Direct a scene, not a slideshow.",
    points: ["Describe camera moves and pacing", "Short clips built for social and story"],
  },
  "image-to-video": {
    headline: "Give stills a pulse.",
    points: ["Start from your own reference image", "Guide the motion with a short prompt"],
  },
};

function FeatureVisual({ mode }: { mode: GenerationMode }) {
  if (mode === "text-to-image") {
    return (
      <div className="relative flex h-full items-center gap-3 p-5">
        <div className="flex-1 rounded-lg border border-line bg-ink-950/80 p-3">
          <Type className="mb-2 size-3.5 text-fg-subtle" aria-hidden />
          <div className="space-y-1.5" aria-hidden>
            <div className="h-1.5 w-full rounded bg-white/15" />
            <div className="h-1.5 w-4/5 rounded bg-white/10" />
            <div className="h-1.5 w-3/5 rounded bg-white/10" />
          </div>
        </div>
        <ArrowRight className="size-4 shrink-0 text-fg-subtle" aria-hidden />
        <Poster tone="noir" className="aspect-[4/5] w-[42%] rounded-lg ring-1 ring-line-strong transition-transform duration-500 group-hover:scale-[1.03]" />
      </div>
    );
  }
  if (mode === "text-to-video") {
    return (
      <div className="relative flex h-full flex-col justify-center gap-2 p-5">
        <Poster tone="tide" className="aspect-[2.4/1] rounded-lg ring-1 ring-line-strong" />
        <div className="grid grid-cols-5 gap-1" aria-hidden>
          {(["tide", "aurora", "dusk", "bloom", "ember"] as const).map((t, i) => (
            <Poster
              key={t}
              tone={t}
              className="aspect-video rounded transition-transform duration-500 group-hover:-translate-y-0.5"
              animated={i === 2}
            />
          ))}
        </div>
      </div>
    );
  }
  return (
    <div className="relative flex h-full items-center justify-center p-5">
      <Poster tone="ember" position="absolute" className="left-[14%] top-1/2 aspect-[4/5] w-[34%] -translate-y-1/2 -rotate-6 rounded-lg opacity-60 ring-1 ring-line-strong" />
      <Poster
        tone="ember"
        animated
        className="ml-[22%] aspect-[4/5] w-[40%] rounded-lg ring-1 ring-violet-soft/50 transition-transform duration-500 group-hover:rotate-1 group-hover:scale-[1.03]"
      />
    </div>
  );
}

export function Features() {
  return (
    <section id="features" className="scroll-mt-20 border-t border-line py-24 sm:py-32">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <Reveal className="max-w-2xl">
          <SectionLabel>Three ways to create</SectionLabel>
          <h2 className="mt-4 text-balance text-3xl font-semibold tracking-[-0.03em] text-fg sm:text-4xl">
            One studio for stills and motion.
          </h2>
          <p className="mt-4 text-pretty leading-relaxed text-fg-muted">
            Switch modes without switching tools. Every mode shares the same prompt editor, framing
            and style controls, so your look stays consistent from first frame to final cut.
          </p>
        </Reveal>

        <div className="mt-14 grid gap-4 md:grid-cols-3">
          {MODES.map((mode, i) => {
            const Icon = mode.icon;
            const detail = DETAILS[mode.id];
            return (
              <Reveal key={mode.id} delay={i * 0.08} className="h-full">
                <article className="group flex h-full flex-col overflow-hidden rounded-xl border border-line bg-ink-900 transition-[border-color,transform] duration-300 hover:-translate-y-1 hover:border-line-strong">
                  <div className="relative h-52 border-b border-line bg-[radial-gradient(80%_80%_at_50%_0%,rgb(99_102_241/0.10),transparent)]">
                    <FeatureVisual mode={mode.id} />
                  </div>
                  <div className="flex flex-1 flex-col p-6">
                    <div className="flex items-center gap-2 text-sm text-fg-muted">
                      <Icon className="size-4 text-violet-soft" aria-hidden />
                      {mode.label}
                    </div>
                    <h3 className="mt-3 text-lg font-medium tracking-tight text-fg">{detail.headline}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-fg-muted">{mode.description}</p>
                    <ul className="mt-5 space-y-2 border-t border-line pt-5 text-sm text-fg-muted">
                      {detail.points.map((point) => (
                        <li key={point} className="flex items-start gap-2.5">
                          <span className="mt-2 size-1 shrink-0 rounded-full bg-violet-soft" aria-hidden />
                          {point}
                        </li>
                      ))}
                    </ul>
                  </div>
                </article>
              </Reveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}
