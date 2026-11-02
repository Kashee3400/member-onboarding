import { NextRequest, NextResponse } from "next/server";

import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  backendJson,
  clearSessionCookies,
  setSessionCookies,
} from "@/lib/server/backend";

const EXPIRY_MARGIN_SECONDS = 30;

type Tokens = { access: string; refresh: string };

// Refresh tokens are single-use, so requests sent with the old one must reuse the result.
const REPLAY_WINDOW_MS = 30_000;
const inFlight = new Map<string, Promise<Tokens | null>>();

function isFresh(token: string | undefined) {
  if (!token) return false;
  try {
    const payload = JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString());
    return payload.exp - EXPIRY_MARGIN_SECONDS > Date.now() / 1000;
  } catch {
    return false;
  }
}

function refreshOnce(refresh: string, request: NextRequest) {
  const existing = inFlight.get(refresh);
  if (existing) return existing;

  const pending = backendJson("/api/v1/auth/refresh/", { refresh }, request)
    .then(({ status, data }) => (status === 200 ? (data as Tokens) : null))
    .catch(() => null)
    .finally(() => setTimeout(() => inFlight.delete(refresh), REPLAY_WINDOW_MS));

  inFlight.set(refresh, pending);
  return pending;
}

function signedOut(request: NextRequest) {
  return request.nextUrl.pathname.startsWith("/api/")
    ? NextResponse.json(
        { error: { code: "not_authenticated", message: "Please sign in." } },
        { status: 401 },
      )
    : NextResponse.redirect(new URL("/login", request.url));
}

/** Keeps the session alive in one place, for pages and API calls alike. */
export async function proxy(request: NextRequest) {
  const access = request.cookies.get(ACCESS_COOKIE)?.value;
  const refresh = request.cookies.get(REFRESH_COOKIE)?.value;

  if (isFresh(access)) return NextResponse.next();
  if (!refresh) return signedOut(request);

  const tokens = await refreshOnce(refresh, request);
  if (!tokens) {
    const response = signedOut(request);
    clearSessionCookies(response);
    return response;
  }

  request.cookies.set(ACCESS_COOKIE, tokens.access);
  request.cookies.set(REFRESH_COOKIE, tokens.refresh);
  const headers = new Headers(request.headers);
  headers.set("cookie", request.cookies.toString());

  const response = NextResponse.next({ request: { headers } });
  setSessionCookies(response, tokens);
  return response;
}

export const config = {
  matcher: ["/((?!_next/|favicon.ico|icon.png|apple-icon.png|brand/|login|forgot-password|reset-password|accept-invite|api/auth/|api/backend/public/).*)"],
};
