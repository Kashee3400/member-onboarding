"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Eraser, ImageUp, PenLine } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState, type PointerEvent } from "react";
import { toast } from "sonner";

import { messageOf } from "@/components/admin/feedback";
import { FileDrop } from "@/components/admin/file-drop";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api/client";

const MB = 1024 * 1024;
const INK = "#14206e";

const STEPS = [
  "Sign on plain white paper with a dark blue or black pen.",
  "Sign large, in the middle, the same way you sign official papers.",
  "Take the photo from straight above, in good light, with no shadow on the paper.",
  "Keep only the signature in the picture: no lines, stamps or fingers.",
];

/** A light checkerboard, so a transparent background is visible as such. */
const CHECKERS =
  "bg-[length:16px_16px] bg-[linear-gradient(45deg,var(--muted)_25%,transparent_25%,transparent_75%,var(--muted)_75%),linear-gradient(45deg,var(--muted)_25%,transparent_25%,transparent_75%,var(--muted)_75%)] bg-[position:0_0,8px_8px]";

function DrawPad({ busy, onSave }: { busy: boolean; onSave: (file: File) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const [empty, setEmpty] = useState(true);

  const point = (event: PointerEvent<HTMLCanvasElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const scale = event.currentTarget.width / box.width;
    return [(event.clientX - box.left) * scale, (event.clientY - box.top) * scale] as const;
  };

  const start = (event: PointerEvent<HTMLCanvasElement>) => {
    const context = event.currentTarget.getContext("2d");
    if (!context) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drawing.current = true;
    context.lineWidth = 5;
    context.lineCap = "round";
    context.lineJoin = "round";
    context.strokeStyle = INK;
    context.beginPath();
    context.moveTo(...point(event));
  };

  const move = (event: PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return;
    const context = event.currentTarget.getContext("2d");
    context?.lineTo(...point(event));
    context?.stroke();
    setEmpty(false);
  };

  const clear = () => {
    const element = canvas.current;
    element?.getContext("2d")?.clearRect(0, 0, element.width, element.height);
    setEmpty(true);
  };

  const save = () =>
    canvas.current?.toBlob((blob) => blob && onSave(new File([blob], "signature.png", { type: "image/png" })), "image/png");

  return (
    <div className="space-y-2">
      <canvas
        ref={canvas}
        width={1200}
        height={400}
        aria-label="Signature pad. Sign here with a mouse, pen or finger."
        className="aspect-[3/1] w-full cursor-crosshair touch-none border bg-white"
        onPointerDown={start}
        onPointerMove={move}
        onPointerUp={() => (drawing.current = false)}
        onPointerLeave={() => (drawing.current = false)}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">A pen or finger on a touch screen gives the best result.</p>
        <div className="flex gap-2">
          <Button type="button" variant="ghost" size="sm" disabled={empty || busy} onClick={clear}>
            <Eraser /> Clear
          </Button>
          <Button type="button" size="sm" disabled={empty || busy} onClick={save}>
            {busy ? "Saving…" : "Save signature"}
          </Button>
        </div>
      </div>
    </div>
  );
}

/**
 * Upload a photo of a signature on paper, or draw one. The server takes the paper away,
 * so what is kept is a transparent PNG holding only the ink.
 */
export function SignatureSetup({ membership, hasSignature }: { membership: string; hasSignature: boolean }) {
  const client = useQueryClient();
  const router = useRouter();
  const [version, setVersion] = useState(() => Date.now());
  const [onFile, setOnFile] = useState(hasSignature);

  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api(`staff/${membership}/signature`, { method: "POST", body: form });
    },
    onSuccess: () => {
      setOnFile(true);
      setVersion(Date.now());
      client.invalidateQueries({ queryKey: ["staff"] });
      client.invalidateQueries({ queryKey: ["signature", membership] });
      router.refresh();
      toast.success("Signature saved. It is used on forms from now on.");
    },
    onError: (error) => toast.error(messageOf(error)),
  });

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-2">
          <p className="text-sm font-medium">For a clean signature</p>
          <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
            {STEPS.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <p className="text-xs text-muted-foreground">
            The paper is removed for you and the signature is saved as a transparent PNG. JPEG, PNG or WEBP, up to 5 MB.
          </p>
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-medium">On file</p>
            {onFile ? (
              <StatusBadge status="active" label="A new one affects future forms only" />
            ) : (
              <StatusBadge status="pending" label="Not added yet" />
            )}
          </div>
          <div className={`flex h-28 items-center justify-center border p-3 ${CHECKERS}`}>
            {onFile ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={`/api/backend/staff/${membership}/signature/file?v=${version}`}
                alt="Your signature as it is printed"
                className="max-h-full max-w-full object-contain"
              />
            ) : (
              <span className="text-sm text-muted-foreground">Your signature will appear here</span>
            )}
          </div>
        </div>
      </div>

      <Tabs defaultValue="photo">
        <TabsList>
          <TabsTrigger value="photo">
            <ImageUp /> Upload a photo
          </TabsTrigger>
          <TabsTrigger value="draw">
            <PenLine /> Draw it here
          </TabsTrigger>
        </TabsList>
        <TabsContent value="photo" className="pt-3">
          <FileDrop
            label={onFile ? "Replace signature" : "Upload signature"}
            accept={[".jpg", ".jpeg", ".png", ".webp"]}
            maxBytes={5 * MB}
            busy={upload.isPending}
            onFile={(file) => upload.mutate(file)}
          />
        </TabsContent>
        <TabsContent value="draw" className="pt-3">
          <DrawPad busy={upload.isPending} onSave={(file) => upload.mutate(file)} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
