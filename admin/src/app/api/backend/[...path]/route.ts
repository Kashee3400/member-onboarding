import { NextRequest, NextResponse } from "next/server";

import {
  ACCESS_COOKIE,
  BACKEND_URL,
  INTERNAL_HEADERS,
  clientAddressHeader,
  forbiddenOrigin,
  isSameOrigin,
} from "@/lib/server/backend";

type Context = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, { params }: Context) {
  if (request.method !== "GET" && !isSameOrigin(request)) return forbiddenOrigin();

  const { path } = await params;
  const access = request.cookies.get(ACCESS_COOKIE)?.value;
  const url = `${BACKEND_URL}/api/v1/${path.map(encodeURIComponent).join("/")}/${request.nextUrl.search}`;
  const body = request.method === "GET" ? undefined : await request.arrayBuffer();

  const response = await fetch(url, {
    method: request.method,
    headers: {
      // Uploads carry their own multipart boundary, which must survive unchanged.
      "Content-Type": request.headers.get("content-type") ?? "application/json",
      ...INTERNAL_HEADERS,
      ...clientAddressHeader(request),
      ...(access ? { Authorization: `Bearer ${access}` } : {}),
    },
    body,
    cache: "no-store",
  });

  if (response.status === 204) return new NextResponse(null, { status: 204 });

  const headers = new Headers({
    "Content-Type": response.headers.get("content-type") ?? "application/json",
  });
  const caching = response.headers.get("cache-control");
  if (caching) headers.set("Cache-Control", caching);
  const disposition = response.headers.get("content-disposition");
  if (disposition) headers.set("Content-Disposition", disposition);
  // Passed on as it arrives, so a ZIP of thousands of forms never sits whole in memory here.
  return new NextResponse(response.body, { status: response.status, headers });
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const PATCH = forward;
export const DELETE = forward;
