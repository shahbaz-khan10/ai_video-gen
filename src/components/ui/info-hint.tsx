import { Info } from "lucide-react";
import { Tooltip } from "./tooltip";

/** Small focusable info icon that reveals a hint on hover or focus. */
export function InfoHint({ label }: { label: string }) {
  return (
    <Tooltip label={label}>
      {(id) => (
        <button
          type="button"
          aria-describedby={id}
          aria-label="More information"
          className="rounded text-fg-subtle transition-colors hover:text-fg focus-visible:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
        >
          <Info className="size-3.5" aria-hidden />
        </button>
      )}
    </Tooltip>
  );
}
