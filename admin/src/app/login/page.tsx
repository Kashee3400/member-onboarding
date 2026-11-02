import type { Metadata } from "next";
import { Suspense } from "react";

import { LoginFlow } from "@/components/auth/login-flow";
import { getBranding } from "@/lib/branding";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage() {
  const organization = process.env.NEXT_PUBLIC_DEFAULT_ORGANIZATION ?? "";
  const branding = await getBranding(organization);
  return (
    <Suspense>
      <LoginFlow branding={branding} organization={organization} />
    </Suspense>
  );
}
