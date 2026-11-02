import type { Metadata } from "next";
import { Suspense } from "react";

import { StatusList } from "@/components/applications/application-table";

export const metadata: Metadata = { title: "Rejected Members" };

export default function RejectedMembersPage() {
  return (
    <Suspense>
      <StatusList kind="rejected" />
    </Suspense>
  );
}
