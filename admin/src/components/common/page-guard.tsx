"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useSession } from "@/hooks/use-session";
import { flatten, isActive } from "@/lib/nav";

import { Forbidden } from "./states";

/**
 * Every page's guard, from the same rules as the sidebar. The page is refused when the
 * closest menu entry above it is one this person may not open, so a typed URL meets a
 * refusal rather than a page of errors. The API refuses anyway.
 */
export function PageGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { navigation, lockedPaths } = useSession();
  const open = flatten(navigation).flatMap(({ item }) => (item.path ? [item.path] : []));
  const closest = [...open, ...lockedPaths]
    .filter((path) => isActive(path, pathname))
    .sort((a, b) => b.length - a.length)[0];
  if (closest && lockedPaths.includes(closest)) return <Forbidden />;
  return <>{children}</>;
}
