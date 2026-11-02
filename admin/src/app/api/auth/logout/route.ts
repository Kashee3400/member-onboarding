import { NextRequest, NextResponse } from "next/server";

import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  backendJson,
  clearSessionCookies,
  forbiddenOrigin,
  isSameOrigin,
} from "@/lib/server/backend";

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) return forbiddenOrigin();

  const access = request.cookies.get(ACCESS_COOKIE)?.value;
  const refresh = request.cookies.get(REFRESH_COOKIE)?.value;
  if (access && refresh) {
    // The cookies go regardless: signing out must work even if the backend is down.
    await backendJson("/api/v1/auth/logout/", { refresh }, request, access).catch(() => null);
  }

  const response = NextResponse.json({ status: "ok" });
  clearSessionCookies(response);
  return response;
}
