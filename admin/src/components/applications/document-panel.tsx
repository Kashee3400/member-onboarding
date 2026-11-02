"use client";

import { ImageOff, ZoomIn } from "lucide-react";
import { useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import type { ApplicationDetail, ApplicationDocument } from "@/lib/types";
import { cn } from "@/lib/utils";

import { FloatingViewer } from "./floating-viewer";
import { Lightbox } from "./lightbox";
import { NumbersCheck, noteFor, type SensitiveNumbers } from "./numbers-check";

/** What a reviewer checks, in reading order. A thumbprint stands in for a signature. */
const SLOTS: { types: string[]; label: string; wide?: boolean; contain?: boolean }[] = [
  { types: ["photo"], label: "Member photo" },
  { types: ["member_signature", "member_thumbprint"], label: "Member signature", contain: true },
  { types: ["aadhaar_front"], label: "Aadhaar front", wide: true },
  { types: ["aadhaar_back"], label: "Aadhaar back", wide: true },
  { types: ["passbook"], label: "Bank passbook", wide: true },
  { types: ["payment_proof"], label: "Payment proof", wide: true },
];

const fileUrl = (id: string) => `/api/backend/documents/${id}/file`;

export function DocumentPanel({
  documents,
  loading,
  numbers,
  application,
  fresh,
  first,
  className,
}: {
  documents: ApplicationDocument[];
  loading: boolean;
  numbers: SensitiveNumbers;
  application?: ApplicationDetail;
  /** Document types sent again since the earlier submission. */
  fresh?: Set<string>;
  /** Document types to bring to the top, as the ones this person is checking. */
  first: string[];
  className?: string;
}) {
  // A click floats the document over the page; a double click, or Full screen, fills it.
  const [floating, setFloating] = useState<number | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const isFirst = (slot: (typeof SLOTS)[number]) => slot.types.some((type) => first.includes(type));
  const slots = [...SLOTS.filter(isFirst), ...SLOTS.filter((slot) => !isFirst(slot))].map((slot) => ({
    ...slot,
    document: documents.find((document) => slot.types.includes(document.document_type)),
  }));
  const items = slots.flatMap((slot) =>
    slot.document
      ? [
          {
            id: slot.document.id,
            label: slot.document.label,
            src: fileUrl(slot.document.id),
            note: noteFor(slot.document.document_type, numbers, application),
          },
        ]
      : [],
  );

  return (
    <aside aria-label="Documents" className={cn("min-w-0", className)}>
      <h2 className="mb-2 text-sm font-medium">Documents</h2>
      <NumbersCheck numbers={numbers} className="mb-2" />
      <div className="flex gap-2 overflow-x-auto pb-1 lg:grid lg:grid-cols-2 lg:overflow-visible lg:pb-0">
        {loading
          ? Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="aspect-4/3 w-36 shrink-0 lg:w-full" />
            ))
          : slots.map((slot) => {
              const document = slot.document;
              const label = document?.label ?? slot.label;
              return (
                <div
                  key={slot.label}
                  className={cn("w-36 shrink-0 lg:w-auto", slot.wide && "lg:col-span-2")}
                >
                  {document ? (
                    <button
                      type="button"
                      onClick={() => setFloating(items.findIndex((item) => item.id === document.id))}
                      onDoubleClick={() => setOpen(items.findIndex((item) => item.id === document.id))}
                      aria-label={`Open ${label}`}
                      title="Click to open beside the form. Double-click for full screen."
                      className="group relative block w-full overflow-hidden border bg-muted outline-none transition-[border-color,box-shadow] hover:border-primary/50 focus-visible:border-primary focus-visible:shadow-(--lift)"
                    >
                      {/* Private, authenticated files, so the image optimizer cannot fetch them. */}
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={fileUrl(document.id)}
                        alt={label}
                        loading="lazy"
                        className={cn(
                          "w-full",
                          slot.wide ? "aspect-16/9 lg:aspect-16/8" : "aspect-4/3",
                          slot.contain ? "bg-white object-contain" : "object-cover",
                        )}
                      />
                      <span className="absolute inset-0 flex items-center justify-center bg-black/35 text-white opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
                        <ZoomIn className="size-5" />
                      </span>
                      {fresh?.has(document.document_type) ? (
                        <span className="absolute top-1 left-1 bg-amber-500 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                          New
                        </span>
                      ) : null}
                    </button>
                  ) : (
                    <div
                      className={cn(
                        "flex w-full items-center justify-center gap-1.5 border border-dashed text-xs text-muted-foreground",
                        slot.wide ? "aspect-16/9 lg:aspect-16/8" : "aspect-4/3",
                      )}
                    >
                      <ImageOff className="size-3.5" /> Not uploaded
                    </div>
                  )}
                  <p className="mt-1 truncate text-xs text-muted-foreground">{label}</p>
                </div>
              );
            })}
      </div>
      <FloatingViewer
        items={items}
        index={floating}
        onIndex={setFloating}
        onClose={() => setFloating(null)}
        onExpand={setOpen}
      />
      <Lightbox items={items} index={open} onIndex={setOpen} onClose={() => setOpen(null)} />
    </aside>
  );
}
