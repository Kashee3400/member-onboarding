import type { Metadata } from "next";
import { Suspense } from "react";

import { PdfCenter } from "@/components/pdf/pdf-center";

export const metadata: Metadata = { title: "PDF Center" };

export default function PdfCenterPage() {
  return (
    <Suspense>
      <PdfCenter />
    </Suspense>
  );
}
