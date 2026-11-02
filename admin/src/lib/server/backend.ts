import { NextRequest, NextResponse } from "next/server";

export const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

/** This hop is inside the private network, while the visitor came over TLS. */
export const INTERNAL_HEADERS = { "X-Forwarded-Proto": "https" };

export const ACCESS_COOKIE = "mo_access";
export const REFRESH_COOKIE = "mo_refresh";
export const MFA_COOKIE = "mo_mfa";

const REFRESH_MAX_AGE = 7 * 24 * 60 * 60;
const MFA_MAX_AGE = 5 * 60;

// Tokens never reach browser JavaScript, so an XSS bug cannot steal a session.
function cookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge,
  } as const;
}

export function setSessionCookies(
  response: NextResponse,
  tokens: { access: string; refresh: string },
) {
  response.cookies.set(ACCESS_COOKIE, tokens.access, cookieOptions(REFRESH_MAX_AGE));
  response.cookies.set(REFRESH_COOKIE, tokens.refresh, cookieOptions(REFRESH_MAX_AGE));
  response.cookies.delete(MFA_COOKIE);
}

export function setMfaCookie(response: NextResponse, token: string) {
  response.cookies.set(MFA_COOKIE, token, cookieOptions(MFA_MAX_AGE));
}

export function clearSessionCookies(response: NextResponse) {
  response.cookies.delete(ACCESS_COOKIE);
  response.cookies.delete(REFRESH_COOKIE);
  response.cookies.delete(MFA_COOKIE);
}

/**
 * Every call reaches the backend from this server, so it must be told who is
 * really calling, or rate limits and the audit log would treat all staff as one.
 * The last address is the one added by the trusted proxy in front of this app.
 */
export function clientAddressHeader(request: NextRequest): Record<string, string> {
  const address = request.headers.get("x-forwarded-for")?.split(",").at(-1)?.trim();
  return address ? { "X-Forwarded-For": address } : {};
}

export async function backendJson(
  path: string,
  body: unknown,
  request: NextRequest,
  bearer?: string,
) {
  const response = await fetch(`${BACKEND_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...INTERNAL_HEADERS,
      ...clientAddressHeader(request),
      ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const text = await response.text();
  return { status: response.status, data: text ? JSON.parse(text) : null };
}

/** Cookies stop other sites sending requests; this stops same-site subdomains too. */
export function isSameOrigin(request: NextRequest) {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  return new URL(origin).host === host;
}

export function forbiddenOrigin() {
  return NextResponse.json(
    { error: { code: "forbidden_origin", message: "Request origin not allowed." } },
    { status: 403 },
  );
}
