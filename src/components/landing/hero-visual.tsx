"use client";

import { motion } from "motion/react";
import { Pause, Sparkles } from "lucide-react";
import { Poster } from "@/components/ui/poster";
import type { PosterTone } from "@/lib/studio-options";

const FRAMES: PosterTone[] = ["dusk", "bloom", "noir", "tide", "aurora", "ember"];

const SETTINGS = [
  ["Mode", "Text to Video"],
  ["Style", "Cinematic"],
  ["Camera", "Slow dolly-in"],
  ["Duration", "8 seconds"],
];

/** Illustrative studio window built entirely from CSS. No generated media. */
export function HeroVisual() {
  return (
    <div className="relative">
      <div
        aria-hidden
        className="absolute -inset-x-10 -top-10 bottom-0 -z-10 bg-[radial-gradient(50%_60%_at_50%_30%,rgb(99_102_241/0.22),transparent_70%)]"
      />
      <div className="overflow-hidden rounded-2xl border border-line-strong bg-ink-900/80 shadow-[0_40px_120px_-40px_rgb(0_0_0/0.9)] backdrop-blur">
        {/* Window chrome */}
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <div className="flex items-center gap-1.5" aria-hidden>
            <span className="size-2.5 rounded-full bg-white/10" />
            <span className="size-2.5 rounded-full bg-white/10" />
            <span className="size-2.5 rounded-full bg-white/10" />
          </div>
          <p className="truncate px-3 font-mono text-[11px] text-fg-subtle">lighthouse_blue_hour.scene</p>
          <span className="rounded-md border border-line px-1.5 py-0.5 font-mono text-[10px] text-fg-subtle">16:9</span>
        </div>

        <div className="grid gap-px bg-line md:grid-cols-[1fr_220px]">
          {/* Viewer */}
          <div className="relative bg-ink-950 p-3 sm:p-4">
            <div className="relative aspect-video overflow-hidden rounded-lg">
              <Poster tone="dusk" animated position="absolute" className="inset-0" />
              <div className="absolute inset-x-0 bottom-0 flex items-center gap-3 bg-linear-to-t from-black/70 to-transparent px-4 pb-3 pt-10">
                <span className="grid size-7 place-items-center rounded-full bg-white/15 backdrop-blur">
                  <Pause className="size-3.5 text-white" aria-hidden />
                </span>
                <div className="relative h-1 flex-1 overflow-hidden rounded-full bg-white/20">
                  <div className="animate-scan absolute inset-y-0 left-0 w-1/4 rounded-full bg-white/80" />
                </div>
                <span className="font-mono text-[10px] text-white/80">00:04 / 00:08</span>
              </div>
              <span className="absolute left-3 top-3 rounded-md bg-black/40 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-white/80 backdrop-blur">
                Illustrative preview
              </span>
            </div>

            {/* Timeline */}
            <div className="mt-3 grid grid-cols-6 gap-1.5" aria-hidden>
              {FRAMES.map((tone, i) => (
                <motion.div
                  key={tone}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.6 + i * 0.06 }}
                  className={i === 0 ? "overflow-hidden rounded-md ring-1 ring-violet-soft" : "overflow-hidden rounded-md"}
                >
                  <Poster tone={tone} className="aspect-video opacity-90" />
                </motion.div>
              ))}
            </div>
          </div>

          {/* Inspector */}
          <div className="hidden flex-col gap-4 bg-ink-900 p-4 text-xs md:flex">
            <div>
              <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-fg-subtle">Prompt</p>
              <p className="leading-relaxed text-fg-muted">
                A lone lighthouse at blue hour, waves in slow motion, warm beam through sea mist…
              </p>
            </div>
            <dl className="grid gap-2.5">
              {SETTINGS.map(([k, v]) => (
                <div key={k} className="flex items-center justify-between border-b border-line pb-2.5">
                  <dt className="text-fg-subtle">{k}</dt>
                  <dd className="text-fg">{v}</dd>
                </div>
              ))}
            </dl>
            <div
              aria-hidden
              className="mt-auto flex items-center justify-center gap-1.5 rounded-lg bg-linear-to-b from-[#8f6bff] to-indigo py-2 font-medium text-white"
            >
              <Sparkles className="size-3.5" />
              Generate
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
