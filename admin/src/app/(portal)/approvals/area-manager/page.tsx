import type { Metadata } from "next";
import { Suspense } from "react";

import { ApprovalQueue } from "@/components/applications/application-table";

export const metadata: Metadata = { title: "AM Approvals" };

export default function AreaManagerApprovalsPage() {
  return (
    <Suspense>
      <ApprovalQueue title="AM Approvals" description="Forms from your MPPs waiting for your check. Oldest first." status="pending_am" />
    </Suspense>
  );
}
