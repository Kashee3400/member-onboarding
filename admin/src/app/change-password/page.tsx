import type { Metadata } from "next";

import { AuthFrame } from "@/components/auth/auth-frame";
import { ChangePasswordForm } from "@/components/auth/password-forms";
import { getBranding } from "@/lib/branding";

export const metadata: Metadata = { title: "Change password" };

export default async function ChangePasswordPage() {
  const branding = await getBranding(process.env.NEXT_PUBLIC_DEFAULT_ORGANIZATION);
  return (
    <AuthFrame
      branding={branding}
      headline={"Keep your\naccount safe"}
      message="A strong password protects the member records you work with."
    >
      <ChangePasswordForm />
    </AuthFrame>
  );
}
