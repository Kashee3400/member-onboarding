import { ApiError, reloadTo } from "@/lib/api";

export { ApiError };

type Query = Record<string, string | number | boolean | null | undefined>;

type Options = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: Query;
  body?: unknown;
  signal?: AbortSignal;
};

function withQuery(path: string, query?: Query) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const text = params.toString();
  return `/api/backend/${path}${text ? `?${text}` : ""}`;
}

/** Calls the backend through the portal's own server, which holds the session. */
export async function api<T>(path: string, { method = "GET", query, body, signal }: Options = {}): Promise<T> {
  const form = typeof FormData !== "undefined" && body instanceof FormData;
  const response = await fetch(withQuery(path, query), {
    method,
    signal,
    headers: form || body === undefined ? undefined : { "Content-Type": "application/json" },
    body: form ? (body as FormData) : body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return undefined as T;

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) {
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      reloadTo(`/login?expired=1&next=${next}`);
    }
    const error = data?.error;
    throw new ApiError(
      response.status,
      error?.code ?? "error",
      error?.message ?? "Something went wrong. Try again.",
      error?.details,
    );
  }
  return data as T;
}

export type Page<T> = {
  next: string | null;
  previous: string | null;
  results: T[];
  /** Numbered pages: how many rows there are in all. */
  count?: number;
  page?: number;
  pages?: number;
};

/** The cursor from a page's `next` URL, for the following request. */
export function cursorOf(url: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url, "http://portal.invalid").searchParams.get("cursor");
  } catch {
    return null;
  }
}
