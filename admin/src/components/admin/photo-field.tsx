"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Camera,
  Crop,
  FlipHorizontal2,
  FlipVertical2,
  ImageUp,
  RotateCcw,
  RotateCcwSquare,
  RotateCwSquare,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ChangeEvent, type DragEvent, type ReactNode } from "react";
import Cropper, { type Area } from "react-easy-crop";
import { toast } from "sonner";

import { messageOf } from "@/components/admin/feedback";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiError } from "@/lib/api/client";
import { apiImage } from "@/lib/api";
import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";

/*
 * A staff photo: pick or drop a picture, then crop (drag, zoom), turn, flip, pick
 * a look and fine-tune light and colour, all in the browser. What is sent is the
 * finished 512 px square, which the server checks and stores as WebP.
 */

const MAX_BYTES = 10 * 1024 * 1024;
/** A big phone photo is scaled to this before editing, so every step stays quick. */
const WORK_SIDE = 2048;
const OUT_SIDE = 512;

type Look = { key: string; label: string; filter: string };

const LOOKS: Look[] = [
  { key: "none", label: "Original", filter: "" },
  { key: "vivid", label: "Vivid", filter: "saturate(1.35) contrast(1.08)" },
  { key: "warm", label: "Warm", filter: "sepia(0.22) saturate(1.2) hue-rotate(-8deg) brightness(1.03)" },
  { key: "cool", label: "Cool", filter: "saturate(1.05) hue-rotate(12deg) brightness(1.04) contrast(1.02)" },
  { key: "soft", label: "Soft", filter: "contrast(0.9) brightness(1.08) saturate(0.85)" },
  { key: "mono", label: "Mono", filter: "grayscale(1) contrast(1.05)" },
  { key: "noir", label: "Noir", filter: "grayscale(1) contrast(1.35) brightness(0.95)" },
  { key: "sepia", label: "Sepia", filter: "sepia(0.75) contrast(1.05)" },
];

type Tune = { brightness: number; contrast: number; saturation: number };
const NEUTRAL: Tune = { brightness: 100, contrast: 100, saturation: 100 };

function filterOf(look: Look, tune: Tune) {
  const parts = [look.filter];
  if (tune.brightness !== 100) parts.push(`brightness(${tune.brightness / 100})`);
  if (tune.contrast !== 100) parts.push(`contrast(${tune.contrast / 100})`);
  if (tune.saturation !== 100) parts.push(`saturate(${tune.saturation / 100})`);
  return parts.filter(Boolean).join(" ") || "none";
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("This picture can't be opened here. Try a JPG or PNG."));
    img.src = src;
  });
}

/** The file as an object URL, scaled down first when it's bigger than needed. */
async function prepare(file: File): Promise<string> {
  const raw = URL.createObjectURL(file);
  const img = await loadImage(raw).catch((e) => {
    URL.revokeObjectURL(raw);
    throw e;
  });
  const side = Math.max(img.naturalWidth, img.naturalHeight);
  if (side <= WORK_SIDE) return raw;
  const scale = WORK_SIDE / side;
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(img.naturalWidth * scale);
  canvas.height = Math.round(img.naturalHeight * scale);
  canvas.getContext("2d")!.drawImage(img, 0, 0, canvas.width, canvas.height);
  URL.revokeObjectURL(raw);
  const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/png"));
  if (!blob) throw new Error("Couldn't read this picture.");
  return URL.createObjectURL(blob);
}

const rad = (deg: number) => (deg * Math.PI) / 180;

/** The crop, cut from the turned, flipped, filtered picture, as a square ≤ 512 px. */
async function render(
  src: string,
  area: Area,
  rotation: number,
  flip: { h: boolean; v: boolean },
  filter: string,
): Promise<Blob> {
  const img = await loadImage(src);
  const r = rad(rotation);
  const w = img.naturalWidth;
  const h = img.naturalHeight;
  const bw = Math.abs(Math.cos(r) * w) + Math.abs(Math.sin(r) * h);
  const bh = Math.abs(Math.sin(r) * w) + Math.abs(Math.cos(r) * h);
  const stage = document.createElement("canvas");
  stage.width = Math.round(bw);
  stage.height = Math.round(bh);
  const ctx = stage.getContext("2d")!;
  ctx.translate(bw / 2, bh / 2);
  ctx.rotate(r);
  ctx.scale(flip.h ? -1 : 1, flip.v ? -1 : 1);
  ctx.translate(-w / 2, -h / 2);
  ctx.filter = filter;
  ctx.drawImage(img, 0, 0);

  const side = Math.min(OUT_SIDE, Math.round(area.width));
  const out = document.createElement("canvas");
  out.width = side;
  out.height = side;
  const octx = out.getContext("2d")!;
  octx.imageSmoothingQuality = "high";
  octx.drawImage(stage, area.x, area.y, area.width, area.height, 0, 0, side, side);
  const blob =
    (await new Promise<Blob | null>((res) => out.toBlob(res, "image/webp", 0.92))) ??
    (await new Promise<Blob | null>((res) => out.toBlob(res, "image/jpeg", 0.92)));
  if (!blob) throw new Error("Couldn't make the picture.");
  return blob;
}

// --- the photo on the account card --------------------------------------------------

/** A person's photo, with a camera button: upload, change or remove it. */
export function PhotoField({
  name,
  photo,
  membership,
  className = "size-16",
}: {
  name: string;
  photo: string | null | undefined;
  membership: string;
  className?: string;
}) {
  const url = `staff/${membership}/photo`;
  const router = useRouter();
  const [current, setCurrent] = useState(photo);
  const avatar = apiImage(current);
  const input = useRef<HTMLInputElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const client = useQueryClient();

  // The signed-in person's own photo comes with the page, so that refreshes too.
  const changed = (next: string | null) => {
    setCurrent(next);
    void client.invalidateQueries({ queryKey: ["queue"] });
    router.refresh();
  };

  const remove = useMutation({
    mutationFn: () => api(url, { method: "DELETE" }),
    onSuccess: () => {
      changed(null);
      toast.success("Photo removed");
    },
    onError: (e) => toast.error(messageOf(e)),
  });

  const open = async (file: File | undefined) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) return toast.error("That isn't a picture.");
    if (file.size > MAX_BYTES) return toast.error("Pick a picture under 10 MB.");
    try {
      setSrc(await prepare(file));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't open this picture.");
    }
  };
  const close = () => {
    if (src) URL.revokeObjectURL(src);
    setSrc(null);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    void open(e.dataTransfer.files?.[0]);
  };

  return (
    <>
      <div
        className="relative shrink-0"
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <Avatar className={cn(className, "transition-shadow", dragging && "ring-2 ring-primary ring-offset-2")}>
          {avatar ? <AvatarImage src={avatar} alt="" /> : null}
          <AvatarFallback className="text-base">{initials(name)}</AvatarFallback>
        </Avatar>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <button
                type="button"
                aria-label="Change photo"
                className="absolute -right-1 -bottom-1 flex size-7 items-center justify-center rounded-full border-2 border-card bg-primary text-primary-foreground shadow-sm transition-transform hover:scale-105"
              />
            }
          >
            <Camera className="size-3.5" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-48">
            <DropdownMenuItem onClick={() => input.current?.click()}>
              <ImageUp /> {avatar ? "Change photo" : "Upload photo"}
            </DropdownMenuItem>
            {avatar ? (
              <DropdownMenuItem variant="destructive" onClick={() => remove.mutate()} disabled={remove.isPending}>
                <Trash2 /> Remove photo
              </DropdownMenuItem>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
        <input
          ref={input}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="hidden"
          onChange={(e: ChangeEvent<HTMLInputElement>) => {
            void open(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </div>
      <Dialog open={!!src} onOpenChange={(o) => (!o ? close() : undefined)}>
        <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-3xl">
          {src ? <Editor
              key={src}
              src={src}
              url={url}
              onSaved={changed}
              onDone={close}
              onPickAnother={() => input.current?.click()}
            /> : null}
        </DialogContent>
      </Dialog>
    </>
  );
}

// --- the editor ----------------------------------------------------------------------

function Slider({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
  show,
  icon,
  neutral,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  show?: (v: number) => string;
  icon?: ReactNode;
  /** Where a double-click puts it back. */
  neutral: number;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="flex items-center justify-between text-xs">
        <span className="flex items-center gap-1.5 font-medium">
          {icon}
          {label}
        </span>
        <span className="text-muted-foreground tabular-nums">{show ? show(value) : value}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        onDoubleClick={() => onChange(neutral)}
        className="h-1.5 w-full cursor-pointer appearance-none bg-muted accent-primary"
      />
    </label>
  );
}

function Editor({
  src,
  url,
  onSaved,
  onDone,
  onPickAnother,
}: {
  src: string;
  url: string;
  onSaved: (photo: string) => void;
  onDone: () => void;
  onPickAnother: () => void;
}) {
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [flip, setFlip] = useState({ h: false, v: false });
  const [look, setLook] = useState<Look>(LOOKS[0]);
  const [tune, setTune] = useState<Tune>(NEUTRAL);
  const [tab, setTab] = useState<"crop" | "looks" | "adjust">("crop");
  const [area, setArea] = useState<Area | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const filter = filterOf(look, tune);

  const onComplete = useCallback((_: Area, px: Area) => setArea(px), []);

  // The result as it will be saved, redrawn a moment after each change.
  useEffect(() => {
    if (!area) return;
    let gone = false;
    const t = setTimeout(() => {
      void render(src, area, rotation, flip, filter)
        .then((blob) => {
          if (gone) return;
          const url = URL.createObjectURL(blob);
          // the old one stays on screen until this one is ready
          setPreview((prev) => {
            if (prev) URL.revokeObjectURL(prev);
            return url;
          });
        })
        .catch(() => undefined);
    }, 180);
    return () => {
      gone = true;
      clearTimeout(t);
    };
  }, [src, area, rotation, flip, filter]);
  const last = useRef<string | null>(null);
  useEffect(() => {
    last.current = preview;
  }, [preview]);
  useEffect(
    () => () => {
      if (last.current) URL.revokeObjectURL(last.current);
    },
    [],
  );

  const save = useMutation({
    mutationFn: async () => {
      if (!area) throw new Error("Move the picture once, then save.");
      const blob = await render(src, area, rotation, flip, filter);
      const form = new FormData();
      form.append("file", blob, blob.type === "image/webp" ? "photo.webp" : "photo.jpg");
      return api<{ photo_url: string }>(url, { method: "POST", body: form });
    },
    onSuccess: ({ photo_url }) => {
      onSaved(photo_url);
      toast.success("Photo updated");
      onDone();
    },
    onError: (e) => toast.error(e instanceof Error && !(e instanceof ApiError) ? e.message : messageOf(e)),
  });

  const reset = () => {
    setCrop({ x: 0, y: 0 });
    setZoom(1);
    setRotation(0);
    setFlip({ h: false, v: false });
    setLook(LOOKS[0]);
    setTune(NEUTRAL);
  };
  const turn = (by: number) => setRotation((r) => ((((r + by + 180) % 360) + 360) % 360) - 180);
  const changed =
    zoom !== 1 ||
    rotation !== 0 ||
    flip.h ||
    flip.v ||
    look.key !== "none" ||
    tune.brightness !== 100 ||
    tune.contrast !== 100 ||
    tune.saturation !== 100;

  return (
    <>
      <DialogHeader>
        <DialogTitle>Edit photo</DialogTitle>
        <DialogDescription>Drag to place it in the circle. Scroll or pinch to zoom.</DialogDescription>
      </DialogHeader>
      <div className="grid gap-4 md:grid-cols-[1fr_17rem]">
        <div className="space-y-3">
          <div className="relative aspect-square w-full overflow-hidden bg-[repeating-conic-gradient(#0000_0_25%,#80808022_0_50%)] bg-[length:20px_20px] bg-neutral-900">
            <Cropper
              image={src}
              crop={crop}
              zoom={zoom}
              rotation={rotation}
              aspect={1}
              cropShape="round"
              showGrid={tab === "crop"}
              minZoom={1}
              maxZoom={5}
              zoomSpeed={0.15}
              onCropChange={setCrop}
              onZoomChange={setZoom}
              onRotationChange={setRotation}
              onCropComplete={onComplete}
              transform={`translate(${crop.x}px, ${crop.y}px) rotate(${rotation}deg) scale(${zoom}) scaleX(${flip.h ? -1 : 1}) scaleY(${flip.v ? -1 : 1})`}
              style={{ mediaStyle: { filter } }}
            />
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Zoom out"
              onClick={() => setZoom((z) => Math.max(1, z - 0.25))}
            >
              <ZoomOut />
            </Button>
            <input
              type="range"
              aria-label="Zoom"
              min={1}
              max={5}
              step={0.01}
              value={zoom}
              onChange={(e) => setZoom(Number(e.target.value))}
              className="h-1.5 flex-1 cursor-pointer appearance-none bg-muted accent-primary"
            />
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Zoom in"
              onClick={() => setZoom((z) => Math.min(5, z + 0.25))}
            >
              <ZoomIn />
            </Button>
          </div>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
            <TabsList className="w-full">
              <TabsTrigger value="crop">
                <Crop /> Crop
              </TabsTrigger>
              <TabsTrigger value="looks">
                <Sparkles /> Looks
              </TabsTrigger>
              <TabsTrigger value="adjust">
                <SlidersHorizontal /> Adjust
              </TabsTrigger>
            </TabsList>
          </Tabs>

          {tab === "crop" ? (
            <div className="space-y-4">
              <Slider
                label="Straighten"
                value={rotation}
                min={-180}
                max={180}
                onChange={setRotation}
                show={(v) => `${v}°`}
                neutral={0}
              />
              <div className="grid grid-cols-2 gap-2">
                <Button variant="outline" size="sm" onClick={() => turn(-90)}>
                  <RotateCcwSquare /> Left
                </Button>
                <Button variant="outline" size="sm" onClick={() => turn(90)}>
                  <RotateCwSquare /> Right
                </Button>
                <Button
                  variant={flip.h ? "secondary" : "outline"}
                  size="sm"
                  aria-pressed={flip.h}
                  onClick={() => setFlip((f) => ({ ...f, h: !f.h }))}
                >
                  <FlipHorizontal2 /> Mirror
                </Button>
                <Button
                  variant={flip.v ? "secondary" : "outline"}
                  size="sm"
                  aria-pressed={flip.v}
                  onClick={() => setFlip((f) => ({ ...f, v: !f.v }))}
                >
                  <FlipVertical2 /> Flip
                </Button>
              </div>
            </div>
          ) : tab === "looks" ? (
            <div className="grid grid-cols-4 gap-2">
              {LOOKS.map((l) => (
                <button
                  key={l.key}
                  type="button"
                  onClick={() => setLook(l)}
                  aria-pressed={look.key === l.key}
                  className="group space-y-1 text-center"
                >
                  <span
                    className={cn(
                      "block aspect-square overflow-hidden rounded-full ring-2 ring-offset-2 ring-offset-popover transition",
                      look.key === l.key ? "ring-primary" : "ring-transparent group-hover:ring-border",
                    )}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={src}
                      alt=""
                      className="size-full object-cover"
                      style={{
                        filter: l.filter || "none",
                        transform: `scaleX(${flip.h ? -1 : 1}) scaleY(${flip.v ? -1 : 1}) rotate(${rotation}deg)`,
                      }}
                    />
                  </span>
                  <span
                    className={cn(
                      "block truncate text-[11px]",
                      look.key === l.key ? "font-semibold" : "text-muted-foreground",
                    )}
                  >
                    {l.label}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <div className="space-y-4">
              <Slider
                label="Brightness"
                value={tune.brightness}
                min={50}
                max={150}
                onChange={(v) => setTune((t) => ({ ...t, brightness: v }))}
                neutral={100}
                show={(v) => `${v - 100 > 0 ? "+" : ""}${v - 100}`}
              />
              <Slider
                label="Contrast"
                value={tune.contrast}
                min={50}
                max={150}
                onChange={(v) => setTune((t) => ({ ...t, contrast: v }))}
                neutral={100}
                show={(v) => `${v - 100 > 0 ? "+" : ""}${v - 100}`}
              />
              <Slider
                label="Saturation"
                value={tune.saturation}
                min={0}
                max={200}
                onChange={(v) => setTune((t) => ({ ...t, saturation: v }))}
                neutral={100}
                show={(v) => `${v - 100 > 0 ? "+" : ""}${v - 100}`}
              />
              <p className="text-[11px] text-muted-foreground">Double-click a slider to put it back.</p>
            </div>
          )}

          <div className="mt-auto flex items-center gap-3 border-t pt-3">
            {/* the result as it will be saved, at the sizes the panel shows it */}
            <Avatar className="size-12">
              {preview ? <AvatarImage src={preview} alt="Preview" /> : null}
              <AvatarFallback />
            </Avatar>
            <Avatar className="size-7">
              {preview ? <AvatarImage src={preview} alt="" /> : null}
              <AvatarFallback />
            </Avatar>
            <p className="text-xs text-muted-foreground">Saved as a 512 px square. This is how it shows in the portal.</p>
          </div>
        </div>
      </div>
      <DialogFooter className="flex-row flex-wrap justify-between gap-2 sm:justify-between">
        <div className="flex gap-2">
          <Button variant="ghost" onClick={reset} disabled={!changed || save.isPending}>
            <RotateCcw /> Reset
          </Button>
          <Button variant="ghost" onClick={onPickAnother} disabled={save.isPending}>
            <ImageUp /> Another picture
          </Button>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={onDone} disabled={save.isPending}>
            Cancel
          </Button>
          <Button onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save photo"}
          </Button>
        </div>
      </DialogFooter>
    </>
  );
}
