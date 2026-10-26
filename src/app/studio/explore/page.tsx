import type { Metadata } from "next";
import Link from "next/link";
import { ArrowUpRight, Compass } from "lucide-react";
import { Reveal } from "@/components/motion/reveal";
import { EmptyState } from "@/components/ui/empty-state";
import { Poster } from "@/components/ui/poster";
import { PageHeader, StudioPage } from "@/components/studio/page-header";
import { SampleBadge, SectionHeading } from "@/components/studio/section-heading";
import { MODES, VISUAL_STYLES } from "@/lib/studio-options";

export const metadata: Metadata = { title: "Explore" };

const STYLE_NOTES: Record<string, string> = {
  cinematic: "Anamorphic framing, motivated light, filmic contrast.",
  dreamlike: "Soft bloom, pastel haze and floating, weightless motion.",
  "neon-noir": "Wet streets, magenta practicals, deep shadow.",
  documentary: "Natural light, honest colour, handheld intimacy.",
  anime: "Clean linework, luminous skies and expressive colour.",
  "golden-hour": "Low warm sun, long shadows and rich amber tones.",
};

export default function ExplorePage() {
  return (
    <StudioPage>
      <PageHeader
        title="Explore"
        description="Browse visual styles to set the tone for your next scene."
        actions={<SampleBadge>Style library</SampleBadge>}
      />

      <ul className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {VISUAL_STYLES.map((style, i) => (
          <li key={style.id}>
            <Reveal delay={i * 0.04}>
              <Link
                href="/studio/create"
                className="group block overflow-hidden rounded-xl border border-line bg-ink-900 transition-[border-color,transform] duration-300 hover:-translate-y-0.5 hover:border-line-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
              >
                <div className="overflow-hidden">
                  <Poster tone={style.tone} className="aspect-[16/10] transition-transform duration-700 ease-out group-hover:scale-[1.05]" />
                </div>
                <div className="flex items-start justify-between gap-3 p-4">
                  <div>
                    <h2 className="text-sm font-medium text-fg">{style.label}</h2>
                    <p className="mt-1 text-xs leading-relaxed text-fg-muted">{STYLE_NOTES[style.id]}</p>
                  </div>
                  <ArrowUpRight className="mt-0.5 size-4 shrink-0 text-fg-subtle transition-colors group-hover:text-fg" aria-hidden />
                </div>
              </Link>
            </Reveal>
          </li>
        ))}
      </ul>

      <div className="mt-12">
        <SectionHeading title="Community showcase" />
        <EmptyState
          icon={Compass}
          title="The showcase is coming soon"
          description={`Shared ${MODES.map((m) => m.short.toLowerCase()).join(", ")} work from other creators will appear here in a later phase.`}
        />
      </div>
    </StudioPage>
  );
}
