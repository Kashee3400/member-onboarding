import { NextRequest, NextResponse } from "next/server";

import {
  backendJson,
  forbiddenOrigin,
  isSameOrigin,
  setMfaCookie,
  setSessionCookies,
} from "@/lib/server/backend";

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) return forbiddenOrigin();

  const { status, data } = await backendJson(
    "/api/v1/auth/login/",
    await request.json(),
    request,
  );
  if (status !== 200) return NextResponse.json(data, { status });

  if (data.mfa_token) {
    const response = NextResponse.json({ status: data.mfa_status });
    setMfaCookie(response, data.mfa_token);
    return response;
  }

  const response = NextResponse.json({ status: "ok" });
  setSessionCookies(response, data);
  return response;
}
