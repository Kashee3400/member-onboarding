"use client";

import { History } from "lucide-react";
import { useMemo, useState } from "react";

import { FormDialog } from "@/components/admin/form-dialog";
import {
  DataTable,
  FilterSelect,
  type Column,
} from "@/components/common/data-table";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { useMe } from "@/hooks/use-session";
import { dateTime } from "@/lib/format";
import type { AuditEvent } from "@/lib/types";

const shortId = (id: string | null | undefined) => (id ? id.slice(-8) : "—");

function EventDetail({
  event,
  actor,
  onClose,
}: {
  event: AuditEvent;
  actor: string;
  onClose: () => void;
}) {
  const rows: [string, string][] = [
    ["When", dateTime(event.occurred_at)],
    ["Who", actor],
    [
      "Target",
      event.target_type ? `${event.target_type} ${event.target_id}` : "—",
    ],
    ["IP address", event.ip_address ?? "—"],
  ];
  return (
    <FormDialog
      title={<span className="font-mono text-sm">{event.action}</span>}
      onClose={onClose}
      footer={
        <Button type="button" variant="ghost" onClick={onClose}>
          Close
        </Button>
      }
    >
      <dl className="grid grid-cols-[6rem_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-sm">
        {rows.map(([name, value]) => (
          <div key={name} className="contents">
            <dt className="text-muted-foreground">{name}</dt>
            <dd className="break-all">{value}</dd>
          </div>
        ))}
      </dl>
      {Object.keys(event.metadata).length ? (
        <pre className="max-h-64 overflow-auto bg-muted p-3 font-mono text-xs whitespace-pre-wrap">
          {JSON.stringify(event.metadata, null, 2)}
        </pre>
      ) : null}
    </FormDialog>
  );
}

// Every way someone sees a member's personal data, for a data protection review.
const PERSONAL_DATA = [
  "document.viewed",
  "application.numbers_viewed",
  "application.pdf_downloaded",
  "application.pdf_previewed",
  "application.data_exported",
  "report.exported",
  "report.pdf_batch_downloaded",
].join(",");

export default function AuditPage() {
  const me = useMe();
  const [open, setOpen] = useState<AuditEvent | null>(null);

  const actorOf = (event: AuditEvent) => {
    if (!event.actor_id) return "System";
    return event.actor_id === me.id
      ? "You"
      : event.actor_name || `Staff …${shortId(event.actor_id)}`;
  };

  const columns = useMemo<Column<AuditEvent>[]>(
    () => [
      {
        id: "when",
        header: "When",
        required: true,
        sortKey: "occurred_at",
        csv: (row) => dateTime(row.occurred_at),
        cell: (row) => (
          <span className="whitespace-nowrap tabular-nums">
            {dateTime(row.occurred_at)}
          </span>
        ),
      },
      {
        id: "action",
        header: "Action",
        sortKey: "action",
        csv: (row) => row.action,
        cell: (row) => <span className="font-mono text-xs">{row.action}</span>,
      },
      {
        id: "actor",
        header: "Who",
        csv: (row) => row.actor_name || row.actor_id || "System",
        cell: (row) => (
          <span className="text-muted-foreground">{actorOf(row)}</span>
        ),
      },
      {
        id: "target",
        header: "Target",
        hideBelow: "md",
        csv: (row) => `${row.target_type} ${row.target_id}`.trim(),
        cell: (row) => (
          <span className="text-muted-foreground">
            {row.target_type || "—"}
            {row.target_id ? (
              <span className="ml-1 font-mono text-xs">
                …{shortId(row.target_id)}
              </span>
            ) : null}
          </span>
        ),
      },
      {
        id: "ip",
        header: "IP address",
        hideBelow: "lg",
        csv: (row) => row.ip_address ?? "",
        cell: (row) => (
          <span className="font-mono text-xs text-muted-foreground">
            {row.ip_address ?? "—"}
          </span>
        ),
      },
      {
        id: "details",
        header: "Details",
        defaultHidden: true,
        csv: (row) => JSON.stringify(row.metadata),
        cell: (row) => (
          <code className="line-clamp-1 max-w-64 text-xs text-muted-foreground">
            {Object.keys(row.metadata).length
              ? JSON.stringify(row.metadata)
              : "—"}
          </code>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [me.id],
  );

  return (
    <>
      <PageHeader
        title="Audit Log"
        description="A permanent record of who did what. Press a row for its details."
      />
      <DataTable<AuditEvent>
        id="audit"
        endpoint="audit/events"
        columns={columns}
        rowKey={(row) => row.id}
        searchPlaceholder="Search action or target"
        filters={({ filters, setFilter }) => (
          <FilterSelect
            label="Show"
            allLabel="Everything"
            value={filters.action__in}
            onChange={(value) => setFilter("action__in", value)}
            options={{ [PERSONAL_DATA]: "Personal data looked at" }}
          />
        )}
        defaultOrdering="-occurred_at"
        exportName="audit-log"
        onRowClick={setOpen}
        empty={
          <EmptyState
            icon={History}
            title="No events found"
            description="Try another search."
          />
        }
      />
      {open ? (
        <EventDetail
          event={open}
          actor={actorOf(open)}
          onClose={() => setOpen(null)}
        />
      ) : null}
    </>
  );
}
