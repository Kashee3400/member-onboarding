import { NextRequest, NextResponse } from "next/server";

import {
  MFA_COOKIE,
  backendJson,
  forbiddenOrigin,
  isSameOrigin,
  setSessionCookies,
} from "@/lib/server/backend";

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) return forbiddenOrigin();

  const body = await request.json();
  const { status, data } = await backendJson(
    "/api/v1/auth/mfa/verify/",
    { ...body, mfa_token: request.cookies.get(MFA_COOKIE)?.value ?? "" },
    request,
  );
  if (status !== 200) return NextResponse.json(data, { status });

  const response = NextResponse.json({ status: "ok" });
  setSessionCookies(response, data);
  return response;
}
