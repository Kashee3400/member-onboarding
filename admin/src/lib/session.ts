import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

import { ACCESS_COOKIE, BACKEND_URL, INTERNAL_HEADERS } from "@/lib/server/backend";
import type { Me, NavItem } from "@/lib/types";

async function backendGet<T>(path: string, access: string): Promise<T> {
  const response = await fetch(`${BACKEND_URL}/api/v1/${path}`, {
    headers: { ...INTERNAL_HEADERS, Authorization: `Bearer ${access}` },
    cache: "no-store",
  });
  if (response.status === 401) redirect("/login");
  if (response.status === 403) {
    const body = await response.json().catch(() => null);
    if (body?.error?.code === "password_change_required") redirect("/change-password");
  }
  if (!response.ok) throw new Error(`Backend returned ${response.status} for ${path}`);
  return response.json();
}

/** The signed-in person and their sidebar, loaded once per page render. */
export const getSession = cache(async () => {
  const access = (await cookies()).get(ACCESS_COOKIE)?.value;
  if (!access) redirect("/login");

  const [me, navigation] = await Promise.all([
    backendGet<Me>("auth/me/", access),
    backendGet<NavItem[]>("auth/me/navigation/", access),
  ]);
  return { me, navigation };
});
