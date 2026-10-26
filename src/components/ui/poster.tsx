import type { PosterTone } from "@/types/studio";
import { cn } from "@/lib/cn";

type Palette = { sky: string; glow: string; far: string; near: string; haze: string };

const PALETTES: Record<PosterTone, Palette> = {
  dusk: { sky: "linear-gradient(180deg,#1b1640 0%,#4b2f7a 45%,#c26b8a 78%,#f2a77a 100%)", glow: "#ffcf9e", far: "#2c2350", near: "#120f22", haze: "#f2a77a" },
  aurora: { sky: "linear-gradient(180deg,#05101f 0%,#0b2a3f 40%,#1c6b6a 70%,#6fd3a8 100%)", glow: "#9ff5d0", far: "#0d2234", near: "#060d16", haze: "#6fd3a8" },
  ember: { sky: "linear-gradient(180deg,#2a120c 0%,#7a2e17 40%,#d9752e 75%,#ffd08a 100%)", glow: "#ffe4b0", far: "#4a1d10", near: "#1c0b06", haze: "#ffb067" },
  tide: { sky: "linear-gradient(180deg,#0a1626 0%,#16365a 45%,#3f7fa8 75%,#a8d3e6 100%)", glow: "#e2f4ff", far: "#14304d", near: "#08121e", haze: "#a8d3e6" },
  noir: { sky: "linear-gradient(180deg,#07060d 0%,#1a0f2e 45%,#5a1f6b 75%,#e0468f 100%)", glow: "#ff7ab8", far: "#1a1030", near: "#07050d", haze: "#7c3aed" },
  bloom: { sky: "linear-gradient(180deg,#140f2a 0%,#3b2a6b 40%,#9c7ad6 72%,#f5c4e4 100%)", glow: "#fff0fb", far: "#2e2357", near: "#120d26", haze: "#e9b6ff" },
};

type PosterProps = {
  tone: PosterTone;
  className?: string;
  /** Slowly drifts the light source. Disabled automatically for reduced motion. */
  animated?: boolean;
  /** Use "absolute" when the caller positions the poster itself. */
  position?: "relative" | "absolute";
};

/** A CSS/SVG-generated cinematic landscape used as placeholder artwork. */
export function Poster({ tone, className, animated = false, position = "relative" }: PosterProps) {
  const p = PALETTES[tone];
  return (
    <div aria-hidden className={cn("grain overflow-hidden", position, className)} style={{ background: p.sky }}>
      <div
        className={cn("absolute left-[58%] top-[44%] size-[38%] -translate-x-1/2 -translate-y-1/2 rounded-full blur-2xl", animated && "animate-drift")}
        style={{ background: `radial-gradient(circle, ${p.glow} 0%, transparent 65%)`, opacity: 0.75 }}
      />
      <div
        className="absolute left-[58%] top-[52%] aspect-square w-[11%] -translate-x-1/2 -translate-y-1/2 rounded-full"
        style={{ background: p.glow, boxShadow: `0 0 40px 8px ${p.glow}66` }}
      />
      <svg viewBox="0 0 400 200" preserveAspectRatio="none" className="absolute inset-x-0 bottom-0 h-[55%] w-full">
        <path d="M0 120 L60 88 L110 104 L170 64 L230 100 L290 76 L340 96 L400 80 L400 200 L0 200Z" fill={p.far} opacity="0.9" />
        <path d="M0 150 L50 128 L120 146 L190 118 L260 150 L330 126 L400 142 L400 200 L0 200Z" fill={p.near} />
      </svg>
      <div className="absolute inset-x-0 bottom-[30%] h-[18%] opacity-30 blur-xl" style={{ background: p.haze }} />
      <div className="absolute inset-0 bg-[radial-gradient(120%_90%_at_50%_40%,transparent_55%,rgb(0_0_0/0.55))]" />
    </div>
  );
}
