/** A full reload on purpose: signing in or out must discard everything held in memory. */
export function reloadTo(path: string) {
  window.location.href = path;
}

/** Images from the API, which the browser reaches through this portal. */
export const apiImage = (url: string | null | undefined) => url?.replace(/^\/api\/v1\//, "/api/backend/");

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: unknown = null,
  ) {
    super(message);
  }

  /** The most useful line for a person: the first field error, if any. */
  get summary() {
    if (this.details && typeof this.details === "object") {
      const first = Object.entries(this.details as Record<string, unknown>)[0];
      if (first) {
        const [field, problem] = first;
        const text = Array.isArray(problem) ? problem[0] : problem;
        return field === "detail" || field === "non_field_errors" ? `${text}` : `${field}: ${text}`;
      }
    }
    return this.message;
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (response.status === 204) return undefined as T;

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = data?.error;
    if (response.status === 401 && !url.startsWith("/api/auth/")) reloadTo("/login");
    throw new ApiError(
      response.status,
      error?.code ?? "error",
      error?.message ?? "Something went wrong.",
      error?.details,
    );
  }
  return data as T;
}

export const auth = (path: string, body?: unknown) =>
  request<{
    status?: string;
    recovery_codes?: string[];
    secret?: string;
    otpauth_uri?: string;
  }>(
    `/api/auth/${path}`,
    { method: "POST", body: JSON.stringify(body ?? {}) },
  );

export const api = {
  get: <T>(path: string) => request<T>(`/api/backend/${path}`),
  post: <T>(path: string, body?: unknown) =>
    request<T>(`/api/backend/${path}`, { method: "POST", body: JSON.stringify(body ?? {}) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(`/api/backend/${path}`, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(`/api/backend/${path}`, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(`/api/backend/${path}`, { method: "DELETE" }),
  upload: async <T>(path: string, form: FormData): Promise<T> => {
    const response = await fetch(`/api/backend/${path}`, { method: "POST", body: form });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const error = data?.error;
      throw new ApiError(
        response.status,
        error?.code ?? "error",
        error?.message ?? "Upload failed.",
        error?.details,
      );
    }
    return data as T;
  },
};
