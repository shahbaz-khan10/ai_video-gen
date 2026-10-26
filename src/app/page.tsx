import { Features } from "@/components/landing/features";
import { Hero } from "@/components/landing/hero";
import { SiteFooter } from "@/components/landing/site-footer";
import { SiteHeader } from "@/components/landing/site-header";
import { ClosingCta, Workflow } from "@/components/landing/workflow";

export default function Home() {
  return (
    <>
      <SiteHeader />
      <main id="main" className="flex-1">
        <Hero />
        <Features />
        <Workflow />
        <ClosingCta />
      </main>
      <SiteFooter />
    </>
  );
}
