/** True when the OS or the in-app preference asks for reduced motion. */
export function prefersReducedMotion() {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
    document.querySelector("[data-reduce-motion]") !== null
  );
}
