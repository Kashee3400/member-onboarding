import type { Metadata } from "next";

import { AuthFrame } from "@/components/auth/auth-frame";
import { ForgotPasswordForm } from "@/components/auth/password-forms";
import { getBranding } from "@/lib/branding";

export const metadata: Metadata = { title: "Reset password" };

export default async function ForgotPasswordPage() {
  const organization = process.env.NEXT_PUBLIC_DEFAULT_ORGANIZATION ?? "";
  const branding = await getBranding(organization);
  return (
    <AuthFrame
      branding={branding}
      headline={"Back in\nin a moment"}
      message="We will email you a link that works for one hour."
    >
      <ForgotPasswordForm organization={organization} domain={branding.email_domain} />
    </AuthFrame>
  );
}
