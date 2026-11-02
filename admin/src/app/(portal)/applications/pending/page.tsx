import type { Metadata } from "next";
import { Suspense } from "react";

import { StatusList } from "@/components/applications/application-table";

export const metadata: Metadata = { title: "Pending Members" };

export default function PendingMembersPage() {
  return (
    <Suspense>
      <StatusList kind="pending" />
    </Suspense>
  );
}
