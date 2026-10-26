"use client";

import { DURATIONS } from "@/lib/studio-options";
import type { ClipDuration } from "@/types/studio";
import { OptionGroup } from "./option-group";

export function DurationSelector({ value, onChange }: { value: ClipDuration; onChange: (v: ClipDuration) => void }) {
  return (
    <OptionGroup
      legend="Clip length"
      hint="Shorter clips usually hold together better. Length limits will depend on the connected model."
      options={DURATIONS}
      value={value}
      onChange={onChange}
      className="grid-cols-3"
      renderOption={(id) => <span className="block py-2 text-center text-xs font-medium">{id}</span>}
    />
  );
}
