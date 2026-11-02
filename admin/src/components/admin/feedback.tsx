"use client";

import { AlertTriangle } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { ApiError } from "@/lib/api";

export function messageOf(error: unknown): string {
  return error instanceof ApiError ? error.summary : "Something went wrong. Try again.";
}

/** A failure beside the form that caused it, so the person keeps what they typed. */
export function FormError({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <Alert variant="destructive">
      <AlertTriangle />
      <AlertDescription>{typeof error === "string" ? error : messageOf(error)}</AlertDescription>
    </Alert>
  );
}
