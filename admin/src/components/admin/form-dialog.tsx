"use client";

import type { FormEvent, ReactNode } from "react";

import { FormError } from "@/components/admin/feedback";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

/**
 * A dialog that stays usable when its content is long: the heading and the buttons
 * hold still and the middle scrolls. With `onSubmit`, the whole thing is one form.
 */
export function FormDialog({
  title,
  description,
  onClose,
  onSubmit,
  error,
  footer,
  className,
  children,
}: {
  title: ReactNode;
  description?: ReactNode;
  onClose: () => void;
  onSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  /** Stays in view above the buttons, however far the middle has scrolled. */
  error?: unknown;
  footer?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  const body = (
    <>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">{children}</div>
      {error ? (
        <div className="border-t p-3">
          <FormError error={error} />
        </div>
      ) : null}
      {footer ? (
        <div className="flex flex-wrap items-center justify-end gap-2 border-t bg-muted/40 p-3">{footer}</div>
      ) : null}
    </>
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className={cn("flex max-h-[90svh] flex-col gap-0 p-0 sm:max-w-lg", className)}>
        <DialogHeader className="border-b p-4 pr-10">
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        {onSubmit ? (
          <form onSubmit={onSubmit} className="flex min-h-0 flex-1 flex-col">
            {body}
          </form>
        ) : (
          body
        )}
      </DialogContent>
    </Dialog>
  );
}
