import type { Metadata } from "next";
import { Suspense } from "react";

import { ApprovalQueue } from "@/components/applications/application-table";

export const metadata: Metadata = { title: "CS & Legal Approvals" };

export default function CsLegalApprovalsPage() {
  return (
    <Suspense>
      <ApprovalQueue title="CS & Legal Approvals" description="Forms the Area Manager has approved. Oldest first." status="pending_cs" />
    </Suspense>
  );
}
