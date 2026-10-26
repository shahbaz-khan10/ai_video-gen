"use client";

import { motion } from "motion/react";
import { ArrowRight } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import { HeroVisual } from "./hero-visual";

const rise = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0 },
};

export function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div aria-hidden className="bg-grid absolute inset-0 [mask-image:radial-gradient(70%_60%_at_50%_0%,black,transparent)]" />
      <div
        aria-hidden
        className="absolute left-1/2 top-0 h-[480px] w-[900px] -translate-x-1/2 bg-[radial-gradient(closest-side,rgb(139_92_246/0.16),transparent)]"
      />

      <motion.div
        initial="hidden"
        animate="show"
        transition={{ staggerChildren: 0.08 }}
        className="relative mx-auto max-w-6xl px-4 pb-16 pt-16 text-center sm:px-6 sm:pt-24"
      >
        <motion.p
          variants={rise}
          className="mx-auto mb-6 inline-flex items-center gap-2 rounded-full border border-line-strong bg-white/[0.03] px-3 py-1 text-xs text-fg-muted"
        >
          <span className="size-1.5 rounded-full bg-violet-soft" aria-hidden />
          Text to Image · Text to Video · Image to Video
        </motion.p>

        <motion.h1
          variants={rise}
          className="mx-auto max-w-4xl text-balance text-[2.6rem] font-semibold leading-[1.04] tracking-[-0.035em] text-fg sm:text-6xl lg:text-7xl"
        >
          Turn Your Imagination{" "}
          <span className="font-display text-[1.08em] font-normal italic tracking-[-0.01em] text-gradient">
            Into Motion.
          </span>
        </motion.h1>

        <motion.p
          variants={rise}
          className="mx-auto mt-6 max-w-xl text-pretty text-base leading-relaxed text-fg-muted sm:text-lg"
        >
          A focused studio for directing AI imagery and film. Write a scene, pick a look and frame,
          and shape stills or motion in one calm workspace.
        </motion.p>

        <motion.div variants={rise} className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <ButtonLink href="/studio/create" size="lg" className="w-full sm:w-auto">
            Start Creating
            <ArrowRight className="size-4 transition-transform group-hover/button:translate-x-0.5" aria-hidden />
          </ButtonLink>
          <ButtonLink href="/studio" size="lg" variant="secondary" className="w-full sm:w-auto">
            Explore Studio
          </ButtonLink>
        </motion.div>

        <motion.div
          variants={{ hidden: { opacity: 0, y: 32, scale: 0.98 }, show: { opacity: 1, y: 0, scale: 1 } }}
          transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
          className="mx-auto mt-16 max-w-5xl text-left sm:mt-20"
        >
          <HeroVisual />
        </motion.div>
      </motion.div>
    </section>
  );
}
