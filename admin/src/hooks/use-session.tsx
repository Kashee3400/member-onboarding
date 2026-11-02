"use client";

import { createContext, useContext, type ReactNode } from "react";

import type { Branding } from "@/lib/branding-types";
import type { Me, NavItem } from "@/lib/types";

type Session = { me: Me; navigation: NavItem[]; branding: Branding };

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ value, children }: { value: Session; children: ReactNode }) {
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession needs the signed-in layout.");
  return session;
}

export const useMe = () => useSession().me;
export const useBranding = () => useSession().branding;

/** For hiding actions only. The API is what actually enforces each permission. */
export function useCan(permission: string): boolean {
  return useSession().me.permissions.includes(permission);
}
