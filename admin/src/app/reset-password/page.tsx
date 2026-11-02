import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthFrame } from "@/components/auth/auth-frame";
import { ResetPasswordForm } from "@/components/auth/password-forms";
import { getBranding } from "@/lib/branding";

export const metadata: Metadata = { title: "Choose a new password" };

export default async function ResetPasswordPage() {
  const branding = await getBranding(process.env.NEXT_PUBLIC_DEFAULT_ORGANIZATION);
  return (
    <AuthFrame
      branding={branding}
      headline={"Almost\nthere"}
      message="Choose a new password and you can sign in straight away."
    >
      <Suspense>
        <ResetPasswordForm />
      </Suspense>
    </AuthFrame>
  );
}
