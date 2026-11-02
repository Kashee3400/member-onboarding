"use client";

import { ChevronLeft, ChevronRight, Expand, GripHorizontal, RotateCw, X, ZoomIn, ZoomOut } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type PointerEvent, type WheelEvent } from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/utils";

import type { LightboxItem } from "./lightbox";

type Box = { x: number; y: number; w: number; h: number };

const KEY = "mo-doc-viewer";
const MIN_W = 320;
const MIN_H = 240;
const EDGE = 8;
const MAX_ZOOM = 5;

function remembered(): Box {
  const fallback = { w: 560, h: 420, x: window.innerWidth - 560 - 24, y: 96 };
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? "null") as Box | null;
    return saved && saved.w && saved.h ? saved : fallback;
  } catch {
    return fallback;
  }
}

/** Kept on screen however the window was resized since. */
function onScreen(box: Box): Box {
  const w = Math.min(Math.max(box.w, MIN_W), window.innerWidth - EDGE * 2);
  const h = Math.min(Math.max(box.h, MIN_H), window.innerHeight - EDGE * 2);
  return {
    w,
    h,
    x: Math.min(Math.max(box.x, EDGE), window.innerWidth - w - EDGE),
    y: Math.min(Math.max(box.y, EDGE), window.innerHeight - h - EDGE),
  };
}

/**
 * A document in a small window over the page, so a number can be read off the card
 * while the form stays in view: drag it by its bar, resize it from the corner, zoom
 * with the wheel. A double click opens the full-screen viewer instead.
 */
export function FloatingViewer({
  items,
  index,
  onIndex,
  onClose,
  onExpand,
}: {
  items: LightboxItem[];
  index: number | null;
  onIndex: (index: number) => void;
  onClose: () => void;
  onExpand: (index: number) => void;
}) {
  const [box, setBox] = useState<Box | null>(null);
  const [zoom, setZoom] = useState(1);
  const [turn, setTurn] = useState(0);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const gesture = useRef<{ kind: "move" | "size" | "pan"; x: number; y: number; start: Box; pan: { x: number; y: number } } | null>(
    null,
  );
  const open = index !== null;
  const item = open ? items[index] : null;

  useEffect(() => {
    if (!open || box) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the window size is known only in the browser
    setBox(onScreen(remembered()));
  }, [open, box]);

  useEffect(() => {
    if (!box) return;
    try {
      localStorage.setItem(KEY, JSON.stringify(box));
    } catch {
      // Remembering the place is a convenience only.
    }
  }, [box]);

  useEffect(() => {
    const keep = () => setBox((current) => (current ? onScreen(current) : current));
    window.addEventListener("resize", keep);
    return () => window.removeEventListener("resize", keep);
  }, []);

  const resetView = useCallback(() => {
    setZoom(1);
    setTurn(0);
    setPan({ x: 0, y: 0 });
  }, []);

  const go = (step: number) => {
    if (index === null) return;
    resetView();
    onIndex((index + step + items.length) % items.length);
  };

  const scale = (by: number) =>
    setZoom((value) => {
      const next = Math.min(MAX_ZOOM, Math.max(1, value + by));
      if (next === 1) setPan({ x: 0, y: 0 });
      return next;
    });

  const begin = (kind: "move" | "size" | "pan", event: PointerEvent<HTMLElement>) => {
    if (!box || (kind === "pan" && zoom === 1)) return;
    if ((event.target as HTMLElement).closest("button") && kind !== "size") return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    gesture.current = { kind, x: event.clientX, y: event.clientY, start: box, pan };
  };

  const follow = (event: PointerEvent<HTMLElement>) => {
    const now = gesture.current;
    if (!now) return;
    const dx = event.clientX - now.x;
    const dy = event.clientY - now.y;
    if (now.kind === "move") setBox(onScreen({ ...now.start, x: now.start.x + dx, y: now.start.y + dy }));
    else if (now.kind === "size") setBox(onScreen({ ...now.start, w: now.start.w + dx, h: now.start.h + dy }));
    else setPan({ x: now.pan.x + dx, y: now.pan.y + dy });
  };

  const end = () => {
    gesture.current = null;
  };

  const onWheel = (event: WheelEvent) => scale(event.deltaY < 0 ? 0.25 : -0.25);

  if (!open || !item || !box) return null;

  return createPortal(
    <section
      role="region"
      aria-label={`${item.label}, floating`}
      className="fixed z-40 flex flex-col overflow-hidden border bg-card text-card-foreground shadow-2xl ring-1 ring-black/5"
      style={{ left: box.x, top: box.y, width: box.w, height: box.h }}
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose();
        else if (event.key === "ArrowRight") go(1);
        else if (event.key === "ArrowLeft") go(-1);
      }}
    >
      <header
        className="flex shrink-0 cursor-move touch-none items-center gap-2 border-b bg-muted/60 px-2 py-1.5 select-none"
        onPointerDown={(event) => begin("move", event)}
        onPointerMove={follow}
        onPointerUp={end}
        onDoubleClick={() => onExpand(index)}
        title="Drag to move. Double-click for full screen."
      >
        <GripHorizontal className="size-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium">
            {item.label}
            {items.length > 1 ? (
              <span className="ml-1.5 font-normal text-muted-foreground tabular-nums">
                {index + 1} / {items.length}
              </span>
            ) : null}
          </p>
          {/* Never cut short: this is the number being matched against the card. */}
          {item.note ? <p className="text-sm leading-snug font-semibold break-words tabular-nums">{item.note}</p> : null}
        </div>
        {items.length > 1 ? (
          <>
            <Tool label="Previous document" onClick={() => go(-1)}>
              <ChevronLeft />
            </Tool>
            <Tool label="Next document" onClick={() => go(1)}>
              <ChevronRight />
            </Tool>
          </>
        ) : null}
        <Tool label="Zoom out" onClick={() => scale(-0.5)} disabled={zoom <= 1}>
          <ZoomOut />
        </Tool>
        <Tool label="Zoom in" onClick={() => scale(0.5)} disabled={zoom >= MAX_ZOOM}>
          <ZoomIn />
        </Tool>
        <Tool label="Rotate" onClick={() => setTurn((value) => value + 90)}>
          <RotateCw />
        </Tool>
        <Tool label="Full screen" onClick={() => onExpand(index)}>
          <Expand />
        </Tool>
        <Tool label="Close" onClick={onClose}>
          <X />
        </Tool>
      </header>

      <div
        className={cn(
          "relative min-h-0 flex-1 touch-none overflow-hidden bg-neutral-950 select-none",
          zoom > 1 ? "cursor-grab active:cursor-grabbing" : "cursor-zoom-in",
        )}
        onWheel={onWheel}
        onPointerDown={(event) => begin("pan", event)}
        onPointerMove={follow}
        onPointerUp={end}
        onDoubleClick={() => onExpand(index)}
      >
        {/* Private, authenticated files, so the image optimizer cannot fetch them. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={item.src}
          alt={item.label}
          draggable={false}
          className="absolute inset-0 size-full object-contain"
          style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom}) rotate(${turn}deg)` }}
        />
        <span className="pointer-events-none absolute bottom-1.5 left-2 bg-black/50 px-1.5 py-0.5 text-[11px] text-neutral-200 tabular-nums">
          {Math.round(zoom * 100)}% · wheel to zoom · double-click for full screen
        </span>
      </div>

      <span
        aria-hidden
        className="absolute right-0 bottom-0 size-4 cursor-se-resize touch-none bg-[linear-gradient(135deg,transparent_50%,var(--border)_50%)]"
        onPointerDown={(event) => begin("size", event)}
        onPointerMove={follow}
        onPointerUp={end}
      />
    </section>,
    document.body,
  );
}

function Tool({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      onDoubleClick={(event) => event.stopPropagation()}
      className="flex size-7 shrink-0 items-center justify-center text-muted-foreground outline-none hover:bg-background hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40 [&_svg]:size-4"
    >
      {children}
    </button>
  );
}
