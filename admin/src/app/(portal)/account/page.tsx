"use client";

import { KeyRound } from "lucide-react";
import Link from "next/link";

import { PhotoField } from "@/components/admin/photo-field";
import { SignatureSetup } from "@/components/admin/signature-setup";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useMe } from "@/hooks/use-session";

export default function AccountPage() {
  const me = useMe();
  return (
    <>
      <PageHeader
        title="My account"
        description={me.needs_signature ? "Your photo, signature and sign-in." : "Your photo and sign-in."}
      />
      <Card className="flex-row flex-wrap items-center gap-5 p-5">
        <PhotoField
          name={me.full_name || me.email}
          photo={me.photo_url}
          membership={me.membership_id}
          className="size-20"
        />
        <div className="min-w-0 flex-1">
          <p className="truncate text-lg font-semibold">{me.full_name || me.email}</p>
          <p className="truncate text-sm text-muted-foreground">{me.email}</p>
          <p className="truncate text-sm text-muted-foreground">{(me.role_names ?? me.roles).join(", ")}</p>
        </div>
        <Button variant="outline" nativeButton={false} render={<Link href="/change-password" />}>
          <KeyRound /> Change password
        </Button>
      </Card>
      {me.needs_signature ? (
        <Card id="signature" className="gap-4 p-5">
          <div>
            <h2 className="font-semibold">Signature</h2>
            <p className="text-sm text-muted-foreground">
              Printed on the membership forms you submit or approve, next to your name.
            </p>
          </div>
          <SignatureSetup membership={me.membership_id} hasSignature={me.has_signature} />
        </Card>
      ) : null}
    </>
  );
}
