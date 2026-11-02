import { NextRequest, NextResponse } from "next/server";

import { MFA_COOKIE, backendJson, forbiddenOrigin, isSameOrigin } from "@/lib/server/backend";

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) return forbiddenOrigin();

  const { status, data } = await backendJson(
    "/api/v1/auth/mfa/enroll/",
    { mfa_token: request.cookies.get(MFA_COOKIE)?.value ?? "" },
    request,
  );
  return NextResponse.json(data, { status });
}
