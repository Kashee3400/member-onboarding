"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check } from "lucide-react";
import { useState, type CSSProperties, type FormEvent } from "react";
import { toast } from "sonner";

import { FormError, messageOf } from "@/components/admin/feedback";
import { FileDrop } from "@/components/admin/file-drop";
import { SaveBar, SettingsCard, useUnsavedGuard } from "@/components/admin/settings-form";
import { Field } from "@/components/common/field";
import { PageHeader } from "@/components/common/page-header";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/client";
import type { Branding } from "@/lib/branding-types";
import { cn } from "@/lib/utils";

const MB = 1024 * 1024;
const IMAGE_TYPES = [".png", ".jpg", ".jpeg", ".webp"];
const HEX = /^#[0-9a-fA-F]{6}$/;
const SWATCHES = [
  "#0284C7",
  "#0369A1",
  "#4338CA",
  "#7C3AED",
  "#BE185D",
  "#B91C1C",
  "#C2410C",
  "#F59E0B",
  "#15803D",
  "#0F766E",
  "#334155",
  "#111827",
];
/** Below this, white text on the colour is hard to read. */
const MINIMUM_CONTRAST = 3;

const browserUrl = (url: string | null) => url?.replace(/^\/api\/v1\//, "/api/backend/") ?? null;

function luminance(hex: string) {
  const [r, g, b] = [1, 3, 5].map((at) => {
    const channel = parseInt(hex.slice(at, at + 2), 16) / 255;
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

const contrastWithWhite = (hex: string) => 1.05 / (luminance(hex) + 0.05);

function ColorField({
  label,
  help,
  value,
  warn,
  onChange,
}: {
  label: string;
  help: string;
  value: string;
  warn?: string | null;
  onChange: (value: string) => void;
}) {
  const valid = HEX.test(value);
  return (
    <Field label={label} help={help}>
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-36">
          <span
            className="absolute top-1/2 left-2 z-2 size-5 -translate-y-1/2 ring-1 ring-foreground/15"
            style={{ backgroundColor: valid ? value : "transparent" }}
          />
          <Input
            aria-label={`${label} hex`}
            aria-invalid={!valid}
            value={value}
            maxLength={7}
            className="pl-9 font-mono uppercase"
            onChange={(event) => onChange(event.target.value)}
          />
        </div>
        <div role="radiogroup" aria-label={`${label} swatches`} className="flex flex-wrap gap-1">
          {SWATCHES.map((swatch) => {
            const chosen = swatch.toLowerCase() === value.toLowerCase();
            return (
              <button
                key={swatch}
                type="button"
                role="radio"
                aria-checked={chosen}
                aria-label={swatch}
                onClick={() => onChange(swatch)}
                className={cn(
                  "flex size-7 items-center justify-center ring-1 ring-foreground/10 transition-transform outline-none",
                  "hover:-translate-y-px focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                  chosen && "ring-2 ring-foreground ring-offset-1 ring-offset-card",
                )}
                style={{ backgroundColor: swatch }}
              >
                {chosen ? <Check className="size-3.5 text-white mix-blend-difference" /> : null}
              </button>
            );
          })}
        </div>
      </div>
      {!valid ? <p className="text-xs text-destructive">Use six hex digits, like #0284C7.</p> : null}
      {valid && warn ? (
        <p className="flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-300">
          <AlertTriangle className="size-3.5 shrink-0" /> {warn}
        </p>
      ) : null}
    </Field>
  );
}

function Mark({ logo, name, color, className }: { logo: string | null; name: string; color: string; className?: string }) {
  return logo ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={logo} alt="" className={cn("object-contain", className)} />
  ) : (
    <span
      className={cn("flex items-center justify-center text-[10px] font-bold text-white", className)}
      style={{ backgroundColor: color }}
    >
      {(name || "M").charAt(0).toUpperCase()}
    </span>
  );
}

/** Drawn with the colours being edited, which the page's own theme doesn't have yet. */
function Preview({ form }: { form: Branding }) {
  const primary = HEX.test(form.primary_color) ? form.primary_color : "#0284C7";
  const accent = HEX.test(form.accent_color) ? form.accent_color : "#F59E0B";
  const logo = browserUrl(form.logo_url);
  const image = browserUrl(form.login_image_url);
  const artwork: CSSProperties = image
    ? { backgroundImage: `url(${image})`, backgroundSize: "cover", backgroundPosition: "left center" }
    : { background: `linear-gradient(135deg, ${primary}, ${accent})` };

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
      <figure className="space-y-1">
        <div className="flex h-40 overflow-hidden border bg-background text-[10px]">
          <div className="w-28 shrink-0 border-r bg-sidebar p-2">
            <div className="flex items-center gap-1.5 border-b pb-2">
              <Mark logo={logo} name={form.display_name} color={primary} className="size-5 shrink-0" />
              <span className="truncate font-semibold">{form.display_name || "Member Onboarding"}</span>
            </div>
            <div className="mt-2 flex items-center justify-between border-l-2 px-1.5 py-1 font-medium" style={{ borderColor: primary, backgroundColor: `${primary}14` }}>
              Approvals
              <span className="px-1 font-semibold" style={{ color: accent }}>
                3
              </span>
            </div>
            <div className="px-1.5 py-1 text-muted-foreground">Members</div>
            <div className="px-1.5 py-1 text-muted-foreground">Reports</div>
          </div>
          <div className="flex-1 space-y-1.5 p-2.5">
            <div className="h-2 w-16 bg-muted" />
            <div className="h-8 border bg-card" />
            <span className="inline-block px-2 py-1 font-medium text-white" style={{ backgroundColor: primary }}>
              Approve
            </span>
          </div>
        </div>
        <figcaption className="text-xs text-muted-foreground">The portal</figcaption>
      </figure>
      <figure className="space-y-1">
        <div className="flex h-40 overflow-hidden border bg-background text-[10px]">
          <div className="relative w-1/2 p-2" style={artwork}>
            <Mark logo={logo} name={form.display_name} color={primary} className="size-5" />
            {form.tagline ? (
              <p className="absolute right-2 bottom-2 left-2 line-clamp-2 font-semibold text-white drop-shadow">
                {form.tagline}
              </p>
            ) : null}
          </div>
          <div className="flex flex-1 items-center justify-center p-2">
            <div className="w-full space-y-1 border bg-card p-2 shadow-sm">
              <p className="truncate font-semibold">Sign in</p>
              <div className="h-3 border" />
              <div className="h-3 border" />
              <div className="h-3.5" style={{ backgroundColor: primary }} />
            </div>
          </div>
        </div>
        <figcaption className="text-xs text-muted-foreground">The sign-in page</figcaption>
      </figure>
    </div>
  );
}

function BrandingForm({ value }: { value: Branding }) {
  const client = useQueryClient();
  const [form, setForm] = useState(value);
  // Images save as soon as they are chosen, so only the text and colours can be unsaved,
  // and the images shown always come from the server.
  const text = ({ display_name, tagline, primary_color, accent_color }: Branding) =>
    JSON.stringify([display_name, tagline, primary_color.toLowerCase(), accent_color.toLowerCase()]);
  const dirty = text(form) !== text(value);
  const { dialog } = useUnsavedGuard(dirty);
  const valid = HEX.test(form.primary_color) && HEX.test(form.accent_color);

  const applied = (saved: Branding, message: string) => {
    client.setQueryData(["branding"], saved);
    toast.success(message, { description: "It can take up to a minute to show across the portal." });
  };

  const save = useMutation({
    mutationFn: (body: object) => api<Branding>("organization/branding", { method: "PATCH", body }),
    onSuccess: (saved) => {
      setForm(saved);
      applied(saved, "Branding saved.");
    },
  });
  const upload = useMutation({
    mutationFn: ({ kind, file }: { kind: string; file: File }) => {
      const data = new FormData();
      data.append("file", file);
      return api<Branding>(`organization/branding/${kind}`, { method: "POST", body: data });
    },
    onSuccess: (saved) => applied(saved, "Image saved."),
    onError: (error) => toast.error(messageOf(error)),
  });
  const remove = useMutation({
    mutationFn: (kind: string) => api<Branding>(`organization/branding/${kind}`, { method: "DELETE" }),
    onSuccess: (saved) => applied(saved, "Image removed."),
    onError: (error) => toast.error(messageOf(error)),
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!valid) return;
    const { display_name, tagline, primary_color, accent_color } = form;
    save.mutate({ display_name, tagline, primary_color, accent_color });
  };

  const busyKind = upload.isPending ? upload.variables?.kind : remove.isPending ? remove.variables : null;
  const hardToRead =
    HEX.test(form.primary_color) && contrastWithWhite(form.primary_color) < MINIMUM_CONTRAST
      ? "White text on this colour is hard to read. Choose a darker one."
      : null;

  return (
    <form onSubmit={submit} className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="space-y-4">
        <SettingsCard title="Name" description="Shown in the menu and on the sign-in page.">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Display name" htmlFor="display_name">
              <Input
                id="display_name"
                required
                maxLength={120}
                value={form.display_name}
                onChange={(event) => setForm({ ...form, display_name: event.target.value })}
              />
            </Field>
            <Field label="Tagline" htmlFor="tagline" optional>
              <Input
                id="tagline"
                maxLength={160}
                value={form.tagline}
                onChange={(event) => setForm({ ...form, tagline: event.target.value })}
              />
            </Field>
          </div>
        </SettingsCard>

        <SettingsCard title="Colours" description="Used for the whole portal, in light and dark.">
          <div className="space-y-5">
            <ColorField
              label="Main colour"
              help="Buttons, the current page, and links."
              value={form.primary_color}
              warn={hardToRead}
              onChange={(next) => setForm({ ...form, primary_color: next })}
            />
            <ColorField
              label="Accent colour"
              help="Small highlights, such as notice dots."
              value={form.accent_color}
              onChange={(next) => setForm({ ...form, accent_color: next })}
            />
          </div>
        </SettingsCard>

        <SettingsCard title="Images" description="These save as soon as you choose them.">
          <div className="grid gap-4 md:grid-cols-2">
            <FileDrop
              label="Logo"
              hint="A square image with a clear background works best."
              accept={IMAGE_TYPES}
              maxBytes={2 * MB}
              preview={browserUrl(value.logo_url)}
              busy={busyKind === "logo"}
              onFile={(file) => upload.mutate({ kind: "logo", file })}
              onRemove={() => remove.mutate("logo")}
            />
            <FileDrop
              label="Sign-in image"
              hint="Landscape, 2560 by 1440. Keep the right side calm, as the sign-in box sits there."
              accept={IMAGE_TYPES}
              maxBytes={10 * MB}
              preview={browserUrl(value.login_image_url)}
              previewClassName="w-28 object-cover"
              busy={busyKind === "login_image"}
              onFile={(file) => upload.mutate({ kind: "login_image", file })}
              onRemove={() => remove.mutate("login_image")}
            />
          </div>
        </SettingsCard>

        <FormError error={save.error} />
        <SaveBar dirty={dirty} saving={save.isPending} onDiscard={() => setForm(value)} />
      </div>
      <aside className="space-y-2 lg:sticky lg:top-18">
        <h2 className="text-sm font-medium">Preview</h2>
        <Preview form={{ ...form, logo_url: value.logo_url, login_image_url: value.login_image_url }} />
      </aside>
      {dialog}
    </form>
  );
}

export default function BrandingPage() {
  const branding = useQuery({
    queryKey: ["branding"],
    queryFn: () => api<Branding>("organization/branding"),
  });

  return (
    <>
      <PageHeader title="Branding" description="Your organization's name, colours and images." />
      {branding.error ? <ErrorState error={branding.error} onRetry={() => branding.refetch()} /> : null}
      {branding.isPending ? <ListSkeleton /> : null}
      {branding.data ? <BrandingForm value={branding.data} /> : null}
    </>
  );
}
