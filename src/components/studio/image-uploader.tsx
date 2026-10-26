"use client";

import { useId, useRef, useState, type DragEvent } from "react";
import { ImageUp, RefreshCw, Trash2 } from "lucide-react";
import { InfoHint } from "@/components/ui/info-hint";
import { cn } from "@/lib/cn";
import { formatBytes, type SelectedImage } from "./use-image-selection";

type ImageUploaderProps = {
  image: SelectedImage | null;
  error: string | null;
  accept: string;
  onSelect: (file: File | undefined) => void;
  onClear: () => void;
};

export function ImageUploader({ image, error, accept, onSelect, onClear }: ImageUploaderProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const onDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    setDragging(false);
    onSelect(e.dataTransfer.files[0]);
  };

  return (
    <div>
      <div className="mb-2.5 flex items-center gap-1.5 text-[13px] font-medium text-fg">
        <span id={`${inputId}-label`}>Source image</span>
        <InfoHint label="The first frame to animate. Images stay in your browser and are not uploaded anywhere in this preview." />
      </div>

      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={accept}
        className="peer sr-only"
        aria-labelledby={`${inputId}-label`}
        onChange={(e) => {
          onSelect(e.target.files?.[0]);
          e.target.value = "";
        }}
      />

      {image ? (
        <div className="flex items-center gap-3 rounded-xl border border-line bg-ink-900 p-2.5">
          {/* eslint-disable-next-line @next/next/no-img-element -- local object URL preview */}
          <img src={image.url} alt="Selected source image" className="size-16 shrink-0 rounded-lg object-cover" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm text-fg">{image.name}</p>
            <p className="text-xs text-fg-subtle">{formatBytes(image.size)}</p>
          </div>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            aria-label="Replace image"
            className="grid size-8 place-items-center rounded-md text-fg-muted transition-colors hover:bg-white/5 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
          >
            <RefreshCw className="size-4" aria-hidden />
          </button>
          <button
            type="button"
            onClick={onClear}
            aria-label="Remove image"
            className="grid size-8 place-items-center rounded-md text-fg-muted transition-colors hover:bg-red-500/10 hover:text-red-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
          >
            <Trash2 className="size-4" aria-hidden />
          </button>
        </div>
      ) : (
        <label
          htmlFor={inputId}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            "group flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border border-dashed px-4 py-8 text-center transition-colors",
            "peer-focus-visible:ring-2 peer-focus-visible:ring-violet-soft/70",
            dragging ? "border-violet-soft/70 bg-violet/[0.08]" : "border-line-strong bg-ink-900 hover:border-white/25 hover:bg-ink-850",
          )}
        >
          <span className="grid size-10 place-items-center rounded-lg border border-line-strong bg-ink-800 text-violet-soft transition-transform group-hover:-translate-y-0.5">
            <ImageUp className="size-5" aria-hidden />
          </span>
          <span>
            <span className="block text-sm text-fg">
              <span className="text-violet-soft">Choose an image</span> or drag it here
            </span>
            <span className="mt-1 block text-xs text-fg-subtle">PNG, JPG or WebP · up to 10 MB</span>
          </span>
        </label>
      )}

      {error && (
        <p role="alert" className="mt-2 text-xs text-red-300">
          {error}
        </p>
      )}
    </div>
  );
}
