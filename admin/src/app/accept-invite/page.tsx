import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthFrame } from "@/components/auth/auth-frame";
import { AcceptInviteForm } from "@/components/auth/password-forms";
import { getBranding } from "@/lib/branding";

export const metadata: Metadata = { title: "Accept your invitation" };

export default async function AcceptInvitePage({
  searchParams,
}: {
  searchParams: Promise<{ organization?: string }>;
}) {
  const { organization } = await searchParams;
  const branding = await getBranding(organization || process.env.NEXT_PUBLIC_DEFAULT_ORGANIZATION);
  return (
    <AuthFrame
      branding={branding}
      headline={"Welcome\naboard"}
      message="Choose your password and you are ready to start reviewing forms."
    >
      <Suspense>
        <AcceptInviteForm />
      </Suspense>
    </AuthFrame>
  );
}
