"use client";

import type { ReactNode } from "react";

import { useMe } from "@/hooks/use-session";

import { Forbidden } from "./states";

/**
 * A page's guard: its content only for staff holding `permission` (one of, for
 * a list). The API refuses anyway; this keeps people from a page of errors.
 */
export function RequirePermission({ permission, children }: { permission: string | string[]; children: ReactNode }) {
  const me = useMe();
  const wanted = Array.isArray(permission) ? permission : [permission];
  if (!wanted.some((code) => me.permissions.includes(code))) return <Forbidden />;
  return <>{children}</>;
}
