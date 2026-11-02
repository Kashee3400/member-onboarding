import { NextRequest, NextResponse } from "next/server";

import {
  ACCESS_COOKIE,
  backendJson,
  forbiddenOrigin,
  isSameOrigin,
  setSessionCookies,
} from "@/lib/server/backend";

const ACTIONS = ["change", "forgot", "reset"];

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ action: string }> },
) {
  if (!isSameOrigin(request)) return forbiddenOrigin();

  const { action } = await params;
  if (!ACTIONS.includes(action)) return new NextResponse(null, { status: 404 });

  const { status, data } = await backendJson(
    `/api/v1/auth/password/${action}/`,
    await request.json(),
    request,
    request.cookies.get(ACCESS_COOKIE)?.value,
  );
  if (status >= 300) return NextResponse.json(data, { status });

  const response = NextResponse.json({ status: "ok" });
  // A changed password ends old sessions, so this one moves to fresh tokens.
  if (action === "change") setSessionCookies(response, data);
  return response;
}
