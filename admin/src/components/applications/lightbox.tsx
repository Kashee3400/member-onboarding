"use client";

import { ChevronLeft, ChevronRight, RotateCw, ZoomIn, ZoomOut, Maximize } from "lucide-react";
import { useEffect, useRef, useState, type PointerEvent, type WheelEvent } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";

export type LightboxItem = { id: string; label: string; src: string; note?: string };

const MIN = 1;
const MAX = 5;

/** Documents full size, for reading an Aadhaar number or passbook: zoom, drag, rotate, next. */
export function Lightbox({
  items,
  index,
  onIndex,
  onClose,
}: {
  items: LightboxItem[];
  index: number | null;
  onIndex: (index: number) => void;
  onClose: () => void;
}) {
  const [zoom, setZoom] = useState(1);
  const [turn, setTurn] = useState(0);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number } | null>(null);
  const stage = useRef<HTMLDivElement>(null);

  const reset = () => {
    setZoom(1);
    setTurn(0);
    setOffset({ x: 0, y: 0 });
  };
  const go = (step: number) => {
    if (index === null) return;
    reset();
    onIndex((index + step + items.length) % items.length);
  };
  const scale = (by: number) =>
    setZoom((value) => {
      const next = Math.min(MAX, Math.max(MIN, value + by));
      if (next === MIN) setOffset({ x: 0, y: 0 });
      return next;
    });

  useEffect(() => {
    if (index === null) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "ArrowRight") go(1);
      else if (event.key === "ArrowLeft") go(-1);
      else if (event.key === "+" || event.key === "=") scale(0.5);
      else if (event.key === "-") scale(-0.5);
      else if (event.key.toLowerCase() === "r") setTurn((value) => value + 90);
      else if (event.key === "0") reset();
    };
    // Capture, because the dialog's own focus handling consumes arrow keys.
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  });

  const item = index === null ? null : items[index];

  const onWheel = (event: WheelEvent) => scale(event.deltaY < 0 ? 0.25 : -0.25);
  const onDown = (event: PointerEvent) => {
    if (zoom === 1) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { x: event.clientX - offset.x, y: event.clientY - offset.y };
  };
  const onMove = (event: PointerEvent) => {
    if (drag.current) setOffset({ x: event.clientX - drag.current.x, y: event.clientY - drag.current.y });
  };

  return (
    <Dialog
      open={index !== null}
      onOpenChange={(open) => {
        if (!open) {
          reset();
          onClose();
        }
      }}
    >
      <DialogContent initialFocus={stage} className="flex h-svh max-h-svh w-screen max-w-none! translate-x-0 translate-y-0 flex-col gap-0 border-0 bg-neutral-950 p-0 text-neutral-50 ring-0 top-0 left-0 [&>[data-slot=dialog-close]]:text-neutral-200 [&>[data-slot=dialog-close]]:hover:bg-white/10">
        <div className="flex h-12 shrink-0 items-center gap-3 border-b border-white/10 px-4 pr-12">
          <DialogTitle className="truncate text-sm font-medium">
            {item?.label}
            {item?.note ? (
              <span className="ml-3 bg-white/10 px-2 py-0.5 text-sm font-semibold tabular-nums whitespace-pre">
                {item.note}
              </span>
            ) : null}
          </DialogTitle>
          <DialogDescription className="text-xs text-neutral-400 tabular-nums">
            {index === null ? "" : `${index + 1} of ${items.length}`}
          </DialogDescription>
        </div>

        <div
          ref={stage}
          tabIndex={-1}
          className="relative min-h-0 flex-1 touch-none overflow-hidden outline-none select-none"
          onWheel={onWheel}
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={() => (drag.current = null)}
          style={{ cursor: zoom > 1 ? "grab" : "default" }}
        >
          {item ? (
            // Private, authenticated files, so the image optimizer cannot fetch them.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={item.src}
              alt={item.label}
              draggable={false}
              className="absolute inset-0 size-full object-contain transition-transform duration-100"
              style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom}) rotate(${turn}deg)` }}
            />
          ) : null}
          {items.length > 1 ? (
            <>
              <Step label="Previous document" className="left-3" onClick={() => go(-1)}>
                <ChevronLeft />
              </Step>
              <Step label="Next document" className="right-3" onClick={() => go(1)}>
                <ChevronRight />
              </Step>
            </>
          ) : null}
        </div>

        <div className="flex h-12 shrink-0 items-center justify-center gap-1 border-t border-white/10">
          <Tool label="Zoom out" hint="-" onClick={() => scale(-0.5)} disabled={zoom <= MIN}>
            <ZoomOut />
          </Tool>
          <span className="w-12 text-center text-xs text-neutral-400 tabular-nums">{Math.round(zoom * 100)}%</span>
          <Tool label="Zoom in" hint="+" onClick={() => scale(0.5)} disabled={zoom >= MAX}>
            <ZoomIn />
          </Tool>
          <Tool label="Rotate" hint="R" onClick={() => setTurn((value) => value + 90)}>
            <RotateCw />
          </Tool>
          <Tool label="Fit to screen" hint="0" onClick={reset}>
            <Maximize />
          </Tool>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Tool({
  label,
  hint,
  children,
  ...props
}: { label: string; hint: string } & React.ComponentProps<typeof Button>) {
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      aria-label={label}
      title={`${label} (${hint})`}
      className="text-neutral-200 hover:bg-white/10 hover:text-white"
      {...props}
    >
      {children}
    </Button>
  );
}

function Step({
  label,
  className,
  onClick,
  children,
}: {
  label: string;
  className: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      onPointerDown={(event) => event.stopPropagation()}
      className={`absolute top-1/2 flex size-10 -translate-y-1/2 items-center justify-center bg-black/50 text-neutral-100 outline-none hover:bg-black/80 focus-visible:ring-2 focus-visible:ring-white ${className}`}
    >
      {children}
    </button>
  );
}
