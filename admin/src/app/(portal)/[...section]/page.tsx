import { Construction } from "lucide-react";
import { notFound } from "next/navigation";

import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/states";
import { flatten } from "@/lib/nav";
import { getSession } from "@/lib/session";

/** Sidebar sections whose feature is not built yet. Only reachable with permission. */
export default async function UpcomingSectionPage({ params }: { params: Promise<{ section: string[] }> }) {
  const { section } = await params;
  const { navigation } = await getSession();
  const entry = flatten(navigation).find(({ item }) => item.path === `/${section.join("/")}`);
  if (!entry) notFound();

  return (
    <>
      <PageHeader title={entry.item.label} description={entry.item.description} />
      <EmptyState icon={Construction} title="Coming soon" description="This section isn't ready yet." />
    </>
  );
}
