import type { Metadata } from "next";
import { Suspense } from "react";

import { AllApplications } from "@/components/applications/application-table";

export const metadata: Metadata = { title: "All Applications" };

export default function ApplicationsPage() {
  return (
    <Suspense>
      <AllApplications />
    </Suspense>
  );
}
