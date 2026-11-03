import "server-only";

import type { Branding } from "@/lib/branding-types";
import { BACKEND_URL, INTERNAL_HEADERS } from "@/lib/server/backend";

export type { Branding };

export const DEFAULT_BRANDING: Branding = {
  display_name: "Member Onboarding",
  tagline: "",
  primary_color: "#0284c7",
  accent_color: "#f59e0b",
  logo_url: null,
  login_image_url: null,
  email_domain: "",
};

/** The browser reaches the backend only through this portal. */
const browserUrl = (url: string | null) => url?.replace(/^\/api\/v1\//, "/api/backend/") ?? null;

const HEX = /^#[0-9a-fA-F]{6}$/;

/** Public, so the login page can wear it. A backend that is down costs only the colours. */
export async function getBranding(organization: string | undefined): Promise<Branding> {
  if (!organization) return DEFAULT_BRANDING;
  try {
    const response = await fetch(
      `${BACKEND_URL}/api/v1/public/branding/?organization=${encodeURIComponent(organization)}`,
      { headers: INTERNAL_HEADERS, next: { revalidate: 60 } },
    );
    if (!response.ok) return DEFAULT_BRANDING;
    const found: Branding = { ...DEFAULT_BRANDING, ...(await response.json()) };
    return { ...found, logo_url: browserUrl(found.logo_url), login_image_url: browserUrl(found.login_image_url) };
  } catch {
    return DEFAULT_BRANDING;
  }
}

/** The colours as CSS. Only whole hex values get through, as this lands in a style tag. */
export function brandingCss(branding: Branding): string {
  const brand = HEX.test(branding.primary_color) ? branding.primary_color : DEFAULT_BRANDING.primary_color;
  const accent = HEX.test(branding.accent_color) ? branding.accent_color : DEFAULT_BRANDING.accent_color;
  return `:root{--brand:${brand};--brand-accent:${accent}}`;
}
