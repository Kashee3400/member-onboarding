import type { Metadata } from "next";
import { Suspense } from "react";

import { ApprovalQueue } from "@/components/applications/application-table";

export const metadata: Metadata = { title: "Finance Approvals" };

export default function FinanceApprovalsPage() {
  return (
    <Suspense>
      <ApprovalQueue title="Finance Approvals" description="Record the payment, then approve. Final approval creates the member and their code." status="pending_finance" />
    </Suspense>
  );
}
