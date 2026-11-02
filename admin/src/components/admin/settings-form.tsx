"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Keeps someone from losing edits: closing the tab asks the browser's question,
 * and leaving by any link, or by calling `guard`, asks ours first.
 */
export function useUnsavedGuard(dirty: boolean) {
  const router = useRouter();
  const [pending, setPending] = useState<(() => void) | null>(null);

  useEffect(() => {
    if (!dirty) return;
    const onLeave = (event: BeforeUnloadEvent) => event.preventDefault();
    const onClick = (event: MouseEvent) => {
      if (event.ctrlKey || event.metaKey || event.shiftKey) return;
      const link = (event.target as HTMLElement).closest?.<HTMLAnchorElement>("a[href]");
      if (!link || link.target === "_blank") return;
      const url = new URL(link.href);
      if (url.origin !== location.origin || url.pathname === location.pathname) return;
      event.preventDefault();
      event.stopPropagation();
      setPending(() => () => router.push(url.pathname + url.search));
    };
    window.addEventListener("beforeunload", onLeave);
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("beforeunload", onLeave);
      document.removeEventListener("click", onClick, true);
    };
  }, [dirty, router]);

  const guard = (proceed: () => void) => (dirty ? setPending(() => proceed) : proceed());

  const dialog = (
    <AlertDialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Leave without saving?</AlertDialogTitle>
          <AlertDialogDescription>The changes you made here will be lost.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep editing</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            onClick={() => {
              pending?.();
              setPending(null);
            }}
          >
            Leave
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );

  return { guard, dialog };
}

/** Appears only when there is something to save, and stays in reach on a long page. */
export function SaveBar({
  dirty,
  saving,
  onDiscard,
  label = "Save changes",
}: {
  dirty: boolean;
  saving: boolean;
  onDiscard: () => void;
  label?: string;
}) {
  if (!dirty) return null;
  return (
    <div className="sticky bottom-3 z-10 md:bottom-13 flex flex-wrap items-center justify-between gap-2 border bg-card p-2.5 pl-3.5 shadow-[var(--lift)]">
      <p className="flex items-center gap-2 text-sm">
        <span className="size-2 rounded-full bg-brand-accent" />
        Unsaved changes
      </p>
      <div className="flex gap-2">
        <Button type="button" variant="ghost" disabled={saving} onClick={onDiscard}>
          Discard
        </Button>
        <Button type="submit" disabled={saving}>
          {saving ? "Saving…" : label}
        </Button>
      </div>
    </div>
  );
}

export type SettingsSection = { key: string; label: string; hint?: string; status?: ReactNode };

/** The list of sections beside a settings page, which becomes a strip on a phone. */
export function SettingsNav({
  sections,
  value,
  onChange,
}: {
  sections: SettingsSection[];
  value: string;
  onChange: (key: string) => void;
}) {
  return (
    <nav
      aria-label="Sections"
      className="flex gap-1 overflow-x-auto lg:sticky lg:top-18 lg:flex-col lg:self-start lg:overflow-visible"
    >
      {sections.map((section) => {
        const active = section.key === value;
        return (
          <button
            key={section.key}
            type="button"
            aria-current={active ? "true" : undefined}
            onClick={() => onChange(section.key)}
            className={cn(
              "relative shrink-0 px-3 py-2 text-left text-sm transition-colors outline-none lg:w-full",
              "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset",
              "before:absolute before:inset-y-1 before:left-0 before:w-0.5 before:bg-primary before:opacity-0",
              active ? "bg-primary/8 font-medium before:opacity-100" : "text-muted-foreground hover:bg-muted",
            )}
          >
            <span className="flex items-center justify-between gap-3">
              {section.label}
              {section.status}
            </span>
            {section.hint ? (
              <span className="hidden text-xs font-normal text-muted-foreground lg:block">{section.hint}</span>
            ) : null}
          </button>
        );
      })}
    </nav>
  );
}

export function SettingsCard({
  title,
  description,
  aside,
  children,
}: {
  title: string;
  description?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card className="gap-0 p-0">
      <div className="flex items-start justify-between gap-3 border-b px-4 py-3">
        <div className="min-w-0">
          <h2 className="font-medium">{title}</h2>
          {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
        </div>
        {aside}
      </div>
      <div className="p-4">{children}</div>
    </Card>
  );
}
