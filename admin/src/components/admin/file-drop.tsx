"use client";

import { FileUp, Loader2, Trash2 } from "lucide-react";
import { useRef, useState, type DragEvent, type ReactNode } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const MB = 1024 * 1024;

/** Drop a file or press the box. Size and type are checked before anything is uploaded. */
export function FileDrop({
  label,
  hint,
  accept,
  maxBytes,
  busy,
  preview,
  previewClassName,
  disabled,
  onFile,
  onRemove,
}: {
  label: string;
  hint?: ReactNode;
  /** Extensions, such as [".png", ".jpg"]. */
  accept: string[];
  maxBytes: number;
  busy?: boolean;
  /** An image to show in the box. */
  preview?: string | null;
  previewClassName?: string;
  disabled?: boolean;
  onFile: (file: File) => void;
  onRemove?: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const take = (file: File | undefined) => {
    if (!file) return;
    const name = file.name.toLowerCase();
    if (!accept.some((ending) => name.endsWith(ending))) {
      toast.error(`That file type is not allowed. Use ${accept.join(", ")}.`);
    } else if (file.size > maxBytes) {
      toast.error(`That file is too big. The limit is ${Math.round(maxBytes / MB)} MB.`);
    } else {
      onFile(file);
    }
  };

  const onDrop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setOver(false);
    if (!disabled && !busy) take(event.dataTransfer.files[0]);
  };

  return (
    <div className="space-y-1.5">
      <button
        type="button"
        disabled={disabled || busy}
        onClick={() => input.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        aria-label={label}
        className={cn(
          "flex min-h-28 w-full items-center gap-3 border border-dashed bg-card p-3 text-left transition outline-none",
          "hover:border-primary/60 focus-visible:border-primary focus-visible:shadow-[var(--lift)]",
          "disabled:cursor-not-allowed disabled:opacity-60",
          over && "border-primary bg-primary/5",
        )}
      >
        {preview ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={preview} alt="" className={cn("size-20 shrink-0 object-contain", previewClassName)} />
        ) : (
          <span className="flex size-11 shrink-0 items-center justify-center bg-muted text-muted-foreground">
            {busy ? <Loader2 className="size-5 animate-spin" /> : <FileUp className="size-5" />}
          </span>
        )}
        <span className="min-w-0 text-sm">
          <span className="block font-medium">{busy ? "Uploading…" : label}</span>
          <span className="block text-xs text-muted-foreground">
            Drop a file here, or press to choose. {accept.join(" ")}, up to {Math.round(maxBytes / MB)} MB.
          </span>
        </span>
      </button>
      <div className="flex items-start justify-between gap-2">
        {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : <span />}
        {onRemove && preview ? (
          <Button type="button" variant="ghost" size="xs" disabled={busy} onClick={onRemove}>
            <Trash2 /> Remove
          </Button>
        ) : null}
      </div>
      <input
        ref={input}
        type="file"
        hidden
        accept={accept.join(",")}
        onChange={(event) => {
          take(event.target.files?.[0]);
          event.target.value = "";
        }}
      />
    </div>
  );
}
