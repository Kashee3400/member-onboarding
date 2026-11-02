"use client";

import { Suspense, use } from "react";

import { ApplicationDetail } from "@/components/applications/application-detail";

export default function ApplicationDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <Suspense>
      <ApplicationDetail id={id} />
    </Suspense>
  );
}
