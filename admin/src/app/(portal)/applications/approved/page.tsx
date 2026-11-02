import type { Metadata } from "next";
import { Suspense } from "react";

import { StatusList } from "@/components/applications/application-table";

export const metadata: Metadata = { title: "Approved Members" };

export default function ApprovedMembersPage() {
  return (
    <Suspense>
      <StatusList kind="approved" />
    </Suspense>
  );
}
