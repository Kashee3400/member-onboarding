"use client";

import { Eye, ImageOff } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { ApplicationDetail, ApplicationDocument } from "@/lib/types";
import { cn } from "@/lib/utils";

import { FloatingViewer } from "./floating-viewer";
import { Lightbox } from "./lightbox";
import { noteFor, type SensitiveNumbers } from "./numbers-check";

/** A thumbprint stands in for a signature. */
const LABELS: Record<string, string> = {
  photo: "Profile pic",
  member_signature: "Signature",
  member_thumbprint: "Thumbprint",
  aadhaar_front: "Aadhaar front",
  aadhaar_back: "Aadhaar back",
  passbook: "Bank passbook",
  payment_proof: "Payment slip",
};

const fileUrl = (id: string) => `/api/backend/documents/${id}/file`;

/**
 * The documents of one step, under its fields, each with a View button, as on the
 * old portal. View opens it in a window that floats over the form; double-click
 * fills the screen.
 */
export function StepDocuments({
  types,
  documents,
  numbers,
  application,
  floats = true,
}: {
  /** Document types this step checks. */
  types: string[];
  documents: ApplicationDocument[];
  numbers: SensitiveNumbers;
  application: ApplicationDetail;
  /** False inside a dialog, where a floating window would sit behind it: View fills the screen. */
  floats?: boolean;
}) {
  const [floating, setFloating] = useState<number | null>(null);
  const [full, setFull] = useState<number | null>(null);
  // A signature and a thumbprint are one slot: whichever the member gave.
  const slots = types
    .filter((type) => type !== "member_thumbprint")
    .map((type) => ({
      type,
      document:
        documents.find((item) => item.document_type === type) ??
        (type === "member_signature" ? documents.find((item) => item.document_type === "member_thumbprint") : undefined),
    }));
  const items = slots.flatMap((slot) =>
    slot.document
      ? [
          {
            id: slot.document.id,
            label: LABELS[slot.document.document_type] ?? slot.document.label,
            src: fileUrl(slot.document.id),
            note: noteFor(slot.document.document_type, numbers, application),
          },
        ]
      : [],
  );
  const indexOf = (id: string) => items.findIndex((item) => item.id === id);
  const view = (id: string) => (floats ? setFloating(indexOf(id)) : setFull(indexOf(id)));

  return (
    <Card className="gap-4 p-5">
      <h3 className="text-sm font-semibold">Documents</h3>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(11rem,1fr))] gap-4">
        {slots.map(({ type, document }) => {
          const label = document ? (LABELS[document.document_type] ?? document.label) : LABELS[type];
          const signature = type === "member_signature";
          return (
            <figure key={type} className="min-w-0 space-y-2">
              <figcaption className="text-xs font-medium text-foreground/80">{label}</figcaption>
              {document ? (
                <>
                  <button
                    type="button"
                    onClick={() => view(document.id)}
                    onDoubleClick={() => setFull(indexOf(document.id))}
                    title="Click to open beside the form. Double-click for full screen."
                    className="block w-full overflow-hidden border bg-muted outline-none hover:border-primary/50 focus-visible:border-primary focus-visible:shadow-(--lift)"
                  >
                    {/* Private, authenticated files, so the image optimizer cannot fetch them. */}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={fileUrl(document.id)}
                      alt={label}
                      loading="lazy"
                      className={cn("aspect-4/3 w-full", signature ? "bg-white object-contain" : "object-cover")}
                    />
                  </button>
                  <Button size="sm" className="w-full" onClick={() => view(document.id)}>
                    <Eye /> View
                  </Button>
                </>
              ) : (
                <div className="flex aspect-4/3 w-full items-center justify-center gap-1.5 border border-dashed text-xs text-muted-foreground">
                  <ImageOff className="size-3.5" /> Not uploaded
                </div>
              )}
            </figure>
          );
        })}
      </div>
      <FloatingViewer
        items={items}
        index={floating}
        onIndex={setFloating}
        onClose={() => setFloating(null)}
        onExpand={setFull}
      />
      <Lightbox items={items} index={full} onIndex={setFull} onClose={() => setFull(null)} />
    </Card>
  );
}
