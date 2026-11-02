"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, BadgeCheck, Check, FileDown, RotateCcw, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { ErrorState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { StatusTabs } from "@/components/common/status-tabs";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCan } from "@/hooks/use-session";
import { api } from "@/lib/api/client";
import { date, dateTime, humanize } from "@/lib/format";
import type { ApplicationDetail as Application, ApplicationDocument, FormSchema } from "@/lib/types";
import { cn } from "@/lib/utils";

import { changesOf, type Change, type Changes } from "./changes";
import { STAGE_LABEL, STAGE_PERMISSION, STAGE_QUEUE } from "./constants";
import { CopyButton } from "./copy-button";
import { DecisionBar } from "./decision-bar";
import { DocumentPanel } from "./document-panel";
import { FormNav } from "./form-nav";
import { useSensitiveNumbers } from "./numbers-check";
import { PaymentCard } from "./payment-card";

type SchemaSection = FormSchema["sections"][number];
type SchemaField = SchemaSection["fields"][number];

const ANIMAL_ROWS = [
  ["indigenous", "Indigenous"],
  ["crossbred", "Crossbred"],
  ["buffalo", "Buffalo"],
] as const;
const ANIMAL_COLUMNS = [
  ["heifer", "Heifer"],
  ["dry", "Dry"],
  ["in_milk", "In milk"],
] as const;
const ANIMAL_KEYS = new Set(ANIMAL_ROWS.flatMap(([kind]) => ANIMAL_COLUMNS.map(([state]) => `${kind}_${state}`)));

function shown(field: SchemaField, value: unknown) {
  if (value === true) return "Yes";
  if (value === false) return "No";
  if (value === undefined || value === null || value === "") return null;
  if (field.type === "date") return date(String(value));
  return field.options?.find((option) => option.value === value)?.label ?? String(value);
}

function Facts({ children, className }: { children: React.ReactNode; className?: string }) {
  return <dl className={cn("grid gap-x-5 gap-y-3 sm:grid-cols-2 xl:grid-cols-3", className)}>{children}</dl>;
}

function Fact({
  label,
  children,
  flagged,
  change,
}: {
  label: string;
  children: React.ReactNode;
  flagged?: boolean;
  /** Set when a resubmission changed this, to show what it was. */
  change?: Change;
}) {
  return (
    <div className={cn("min-w-0", change && "-mx-1.5 -my-1 bg-amber-500/10 px-1.5 py-1 ring-1 ring-amber-500/30 ring-inset")}>
      <dt className={cn("text-xs text-muted-foreground", flagged && "font-medium text-destructive")}>
        {label}
        {change ? (
          <span className="ml-1.5 font-medium text-amber-700 dark:text-amber-300">Changed</span>
        ) : null}
      </dt>
      <dd className={cn("text-sm wrap-break-word", flagged && "font-medium text-destructive")}>
        {flagged ? <AlertTriangle className="mr-1 inline size-3.5 align-[-2px]" /> : null}
        {children ?? <span className="text-muted-foreground">—</span>}
      </dd>
      {change ? (
        <p className="mt-0.5 text-xs text-muted-foreground line-through decoration-muted-foreground/50">
          {change.before || "Empty"}
        </p>
      ) : null}
    </div>
  );
}

/** For a form sent again: what changed, and what was asked for but is still the same. */
function ChangesSummary({
  application,
  changes,
  labels,
}: {
  application: Application;
  changes: Changes;
  labels: Record<string, string>;
}) {
  const rejection = application.decisions
    .filter((item) => item.decision === "rejected" && item.revision === changes.since)
    .at(-1);
  const nothing = !changes.fields.length && !changes.documents.size;
  const jump = (section: string) =>
    document.querySelector(`[data-section="${section}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  return (
    <div className="space-y-2 border border-amber-500/30 bg-amber-500/8 px-4 py-3 text-sm">
      <p className="flex items-center gap-2 font-medium">
        <RotateCcw className="size-4 text-amber-600 dark:text-amber-400" />
        Sent again. {nothing ? "Nothing changed" : `${changes.fields.length + changes.documents.size} changes`} since
        submission {changes.since}.
      </p>
      {rejection?.reason ? (
        <p className="text-muted-foreground">
          Rejected then by {rejection.decided_by_name}: “{rejection.reason}”
        </p>
      ) : null}
      {changes.fields.length ? (
        <ul className="flex flex-wrap gap-1.5">
          {changes.fields.map((change) => (
            <li key={change.path}>
              <button
                type="button"
                onClick={() => jump(change.section)}
                className="border bg-background px-2 py-0.5 text-xs outline-none hover:border-amber-500/60 focus-visible:ring-2 focus-visible:ring-ring"
              >
                {change.label}
              </button>
            </li>
          ))}
          {[...changes.documents].map((type) => (
            <li key={type} className="border bg-background px-2 py-0.5 text-xs">
              New {humanize(type).toLowerCase()}
            </li>
          ))}
        </ul>
      ) : null}
      {changes.untouched.length ? (
        <p className="text-destructive">
          Marked last time but not changed:{" "}
          {changes.untouched.map((path) => labels[path] ?? path).join(", ")}
        </p>
      ) : null}
    </div>
  );
}

function Section({
  id,
  title,
  children,
  className,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Card id={`section-${id}`} data-section={id} className={cn("scroll-mt-28 gap-3 p-4", className)}>
      <h2 className="text-sm font-semibold">{title}</h2>
      {children}
    </Card>
  );
}

function FormSection({
  section,
  application,
  changes,
}: {
  section: SchemaSection;
  application: Application;
  changes: Changes;
}) {
  const values = application.data[section.key] ?? {};
  const fields = section.fields.filter(
    (field) => (field.required || values[field.key] !== undefined) && !(section.key === "animals" && ANIMAL_KEYS.has(field.key)),
  );
  return (
    <Section id={section.key} title={section.title}>
      {section.key === "animals" ? <AnimalGrid application={application} /> : null}
      <Facts>
        {section.key === "address" ? <Fact label="Village">{application.place.village_name}</Fact> : null}
        {section.key === "animals" ? (
          <Fact label="Details as on">{application.place.as_on_date ? date(application.place.as_on_date) : null}</Fact>
        ) : null}
        {fields.map((field) => {
          const path = `${section.key}.${field.key}`;
          return (
            <Fact
              key={path}
              label={field.label}
              flagged={application.rejected_fields.includes(path)}
              change={changes.byPath.get(path)}
            >
              {shown(field, values[field.key])}
            </Fact>
          );
        })}
        {section.key === "animals" ? (
          <Fact label="Surplus">
            <span className="font-medium">{application.computed.surplus_lpd} litres a day</span>
          </Fact>
        ) : null}
      </Facts>
    </Section>
  );
}

function AnimalGrid({ application }: { application: Application }) {
  const values = application.data.animals ?? {};
  return (
    <div className="overflow-x-auto border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead />
            {ANIMAL_COLUMNS.map(([key, label]) => (
              <TableHead key={key} className="text-right">
                {label}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {ANIMAL_ROWS.map(([kind, label]) => (
            <TableRow key={kind}>
              <TableCell className="text-muted-foreground">{label}</TableCell>
              {ANIMAL_COLUMNS.map(([state]) => (
                <TableCell key={state} className="text-right tabular-nums">
                  {String(values[`${kind}_${state}`] ?? 0)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

/** The road a form travels, and where this one is. */
function StageTrack({ application }: { application: Application }) {
  const stages = ["pending_am", "pending_cs", "pending_finance"];
  const stopped =
    application.status === "rejected"
      ? application.decisions.find((item) => item.decision === "rejected" && item.revision === application.revision)?.stage
      : undefined;
  const reached =
    application.status === "approved"
      ? 3
      : stopped
        ? stages.indexOf(stopped)
        : stages.indexOf(application.status);
  const steps = [
    { label: "Facilitator", state: application.revision ? "done" : "current" },
    ...stages.map((stage, index) => ({
      label: STAGE_LABEL[stage],
      state: stage === stopped ? "stopped" : index < reached ? "done" : index === reached ? "current" : "todo",
    })),
    { label: "Member", state: application.status === "approved" ? "done" : "todo" },
  ];
  return (
    <ol aria-label="Progress" className="flex items-center gap-1 overflow-x-auto py-0.5">
      {steps.map((step, index) => (
        <li key={step.label} className="flex shrink-0 items-center gap-1">
          {index ? (
            <span aria-hidden className={cn("h-px w-4 sm:w-7", step.state === "todo" ? "bg-border" : "bg-primary/50")} />
          ) : null}
          <span
            aria-current={step.state === "current" ? "step" : undefined}
            className={cn(
              "flex items-center gap-1.5 px-2 py-1 text-xs",
              step.state === "done" && "text-foreground",
              step.state === "todo" && "text-muted-foreground",
              step.state === "current" && "bg-primary/10 font-medium text-primary",
              step.state === "stopped" && "bg-destructive/10 font-medium text-destructive",
            )}
          >
            {step.state === "done" ? (
              <Check className="size-3.5 text-primary" />
            ) : step.state === "stopped" ? (
              <X className="size-3.5" />
            ) : (
              <span className={cn("size-1.5 rounded-full", step.state === "current" ? "bg-primary" : "bg-border")} />
            )}
            {step.label}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** Jumps through a long form, and shows where the reader is. */
function SectionIndex({ sections }: { sections: { id: string; title: string }[] }) {
  const [current, setCurrent] = useState(sections[0]?.id);
  useEffect(() => {
    const seen = new IntersectionObserver(
      (entries) => {
        const top = entries.filter((entry) => entry.isIntersecting).sort(
          (a, b) => a.boundingClientRect.top - b.boundingClientRect.top,
        )[0];
        if (top) setCurrent(top.target.id.replace("section-", ""));
      },
      { rootMargin: "-112px 0px -65% 0px" },
    );
    sections.forEach(({ id }) => {
      const element = document.getElementById(`section-${id}`);
      if (element) seen.observe(element);
    });
    return () => seen.disconnect();
  }, [sections]);

  return (
    <nav
      aria-label="Form sections"
      className="sticky top-14 z-10 -mx-1 flex gap-0.5 overflow-x-auto border-b bg-background/95 px-1 py-1 backdrop-blur scrollbar-none"
    >
      {sections.map((section) => (
        <button
          key={section.id}
          type="button"
          aria-current={current === section.id ? "true" : undefined}
          onClick={() => {
            setCurrent(section.id);
            document.getElementById(`section-${section.id}`)?.scrollIntoView({ behavior: "smooth" });
          }}
          className={cn(
            "shrink-0 px-2.5 py-1 text-xs whitespace-nowrap outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
            current === section.id
              ? "bg-primary/10 font-medium text-primary"
              : "text-muted-foreground hover:bg-muted hover:text-foreground",
          )}
        >
          {section.title}
        </button>
      ))}
    </nav>
  );
}

function PlaceSection({ application }: { application: Application }) {
  const place = application.place;
  return (
    <Section id="place" title="Village details">
      <Facts>
        <Fact label="Name of milk producer">{application.applicant_name}</Fact>
        <Fact label="Pooling point code">{place.mpp_code}</Fact>
        <Fact label="Revenue village">{place.village_name}</Fact>
        <Fact label="MCC">
          {place.mcc_code} {place.mcc_name}
        </Fact>
        <Fact label="BMC">{place.bmc_name || null}</Fact>
        <Fact label="Route">{place.route_name || null}</Fact>
        <Fact label="MPP">
          {place.mpp_code} {place.mpp_name}
        </Fact>
        <Fact label="Revenue village code">{place.village_code}</Fact>
        <Fact label="Tehsil">{place.tehsil || null}</Fact>
        <Fact label="District">{place.district || null}</Fact>
      </Facts>
    </Section>
  );
}

function FamilySection({ family, change }: { family: NonNullable<Application["data"]["family"]>; change?: Change }) {
  return (
    <Section id="family" title={change ? "Household members (changed)" : "Household members"}>
      {change ? (
        <p className="text-xs text-muted-foreground">
          Before: <span className="line-through">{change.before || "none"}</span>
        </p>
      ) : null}
      <div className="overflow-x-auto border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Relation</TableHead>
              <TableHead>Gender</TableHead>
              <TableHead className="text-right">Age</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {family.map((person) => (
              <TableRow key={`${person.name}-${person.relation}`}>
                <TableCell>{person.name}</TableCell>
                <TableCell className="capitalize">{person.relation}</TableCell>
                <TableCell className="capitalize">{person.gender}</TableCell>
                <TableCell className="text-right tabular-nums">{person.age}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </Section>
  );
}

function History({ application }: { application: Application }) {
  const events = [
    ...application.revisions.map((item) => ({
      key: `r-${item.number}`,
      when: item.submitted_at,
      title: `Submission ${item.number} by ${item.submitted_by_name}`,
      note: "",
      tone: "neutral",
    })),
    ...application.decisions.map((item) => ({
      key: item.id,
      when: item.decided_at,
      title: `${humanize(item.decision)} by ${item.decided_by_name}${STAGE_LABEL[item.stage] ? ` (${STAGE_LABEL[item.stage]})` : ""}`,
      note: item.reason,
      tone: item.decision,
    })),
  ].sort((a, b) => b.when.localeCompare(a.when));

  return (
    <Section id="history" title="History">
      {events.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing yet. This form hasn&apos;t been submitted.</p>
      ) : (
        <ol className="space-y-3">
          {events.map((event) => (
            <li key={event.key} className="relative flex gap-3 text-sm">
              <span
                className={cn(
                  "mt-1.5 size-2 shrink-0 rounded-full",
                  event.tone === "approved" ? "bg-emerald-500" : event.tone === "rejected" ? "bg-red-500" : "bg-primary",
                )}
              />
              <span className="min-w-0">
                <span className="block">{event.title}</span>
                <span className="block text-xs text-muted-foreground">{dateTime(event.when)}</span>
                {event.note ? <span className="mt-0.5 block text-muted-foreground">{event.note}</span> : null}
              </span>
            </li>
          ))}
        </ol>
      )}
    </Section>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-12 w-72" />
      <Skeleton className="h-16 w-full" />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_21rem] 2xl:grid-cols-[minmax(0,1fr)_30rem]">
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-44 w-full" />
          ))}
        </div>
        <Skeleton className="h-96 w-full" />
      </div>
    </div>
  );
}

export function ApplicationDetail({ id }: { id: string }) {
  const client = useQueryClient();
  const application = useQuery({
    queryKey: ["application", id],
    queryFn: () => api<Application>(`applications/${id}`),
  });
  const schema = useQuery({
    queryKey: ["form-schema"],
    queryFn: () => api<FormSchema>("applications/form"),
    staleTime: 60 * 60_000,
  });
  const documents = useQuery({
    queryKey: ["application-documents", id],
    queryFn: () => api<ApplicationDocument[]>(`applications/${id}/documents`),
  });
  const numbers = useSensitiveNumbers(id, application.data);
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["application", id] });
    client.invalidateQueries({ queryKey: ["application-documents", id] });
    client.invalidateQueries({ queryKey: ["queue"] });
  };

  const data = application.data;
  const canDecide = useCan(STAGE_PERMISSION[data?.status ?? ""] ?? "");
  const canPrintFull = useCan("applications.download_full_pdf");
  const canPayAtFinance = useCan("applications.approve_finance") && data?.status === "pending_finance";
  const canPayAtAm = useCan("applications.approve_am");

  const [scope, setScope] = useState<"mine" | "all">("mine");
  const familyCount = data?.data.family?.length ?? 0;
  const hasPayment = !!data?.payment.amount || canPayAtFinance || (canPayAtAm && data?.status === "pending_am");

  if (application.error || schema.error) {
    return (
      <ErrorState
        error={application.error ?? schema.error}
        onRetry={() => {
          application.refetch();
          schema.refetch();
        }}
      />
    );
  }
  if (!data || !schema.data) return <DetailSkeleton />;

  const stage = STAGE_LABEL[data.status];
  const canAct = !!stage && canDecide;
  const hasProof = documents.data?.some((item) => item.document_type === "payment_proof") ?? false;
  // Only the Member Fee step waits for these, so the other steps can still go ahead.
  const feeOpen = data.review_steps.some((step) => step.key === "fee" && step.can_approve);
  const blocked = !feeOpen
    ? null
    : !data.payment.amount
      ? "Save the payment details before approving Member Fee."
      : documents.isSuccess && !hasProof
        ? "Upload the payment slip before approving Member Fee."
        : null;
  const back = canAct ? STAGE_QUEUE[data.status] : "/applications";
  const family = data.data.family ?? [];
  const changes = changesOf(data, schema.data, documents.data ?? []);
  const labels: Record<string, string> = Object.fromEntries(
    schema.data.sections.flatMap((section) => section.fields.map((field) => [`${section.key}.${field.key}`, field.label])),
  );

  // Someone reviewing starts on their own steps. Every step stays one click away.
  const mySteps = data.review_steps.filter((step) => step.mine);
  const reviewing = !!stage && mySteps.length > 0;
  const focused = reviewing && scope === "mine";
  const hasContent = (section: string) =>
    section === "family" ? familyCount > 0 : section === "payment" ? hasPayment : true;
  const steps = (focused ? mySteps : data.review_steps).filter((step) => step.sections.some(hasContent));
  const sections = [
    ...steps.map((step) => ({ id: `step-${step.key}`, title: `${step.number}. ${step.title}` })),
    { id: "history", title: "History" },
  ];
  const myFields = {
    ...schema.data,
    sections: schema.data.sections.filter((section) => mySteps.some((step) => step.sections.includes(section.key))),
  };

  return (
    <div className="space-y-4">
      <header className="space-y-3">
        <Link
          href={back}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground outline-none hover:text-foreground focus-visible:text-foreground"
        >
          <ArrowLeft className="size-4" /> {canAct ? "Back to the queue" : "All applications"}
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold tracking-tight">{data.applicant_name || "No name yet"}</h1>
              <StatusBadge status={data.status} label={data.status_label} />
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              <span className="font-mono tabular-nums">{data.form_number || "No form number yet"}</span>
              {" · "}MPP {data.mpp_code} {data.mpp_name}
            </p>
          </div>
          <FormNav id={data.id} status={data.status} steps={steps} />
          {data.status === "approved" ? (
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                nativeButton={false}
                render={
                  <a href={`/api/backend/applications/${id}/pdf?variant=single`} target="_blank" rel="noreferrer" />
                }
              >
                <FileDown /> Single page PDF
              </Button>
              {canPrintFull ? (
                <Button
                  nativeButton={false}
                  render={
                    <a href={`/api/backend/applications/${id}/pdf?variant=full`} target="_blank" rel="noreferrer" />
                  }
                >
                  <FileDown /> Full form PDF
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>
        <StageTrack application={data} />
      </header>

      {data.tr_code ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border border-emerald-500/30 bg-emerald-500/8 px-4 py-3">
          <BadgeCheck className="size-5 text-emerald-600 dark:text-emerald-400" />
          <span className="text-sm text-muted-foreground">Member code</span>
          <span className="inline-flex items-center gap-1">
            <span className="font-mono font-semibold tabular-nums">{data.tr_code}</span>
            <CopyButton value={data.tr_code} label="Copy member code" />
          </span>
        </div>
      ) : null}
      {data.status === "rejected" ? (
        <div className="border border-destructive/30 bg-destructive/8 px-4 py-3 text-sm">
          <p className="font-medium text-destructive">Rejected</p>
          <p>{data.rejection_reason}</p>
          {data.rejected_fields.length ? (
            <p className="mt-1 text-xs text-muted-foreground">
              {data.rejected_fields.length === 1 ? "1 field is" : `${data.rejected_fields.length} fields are`} marked in
              red below.
            </p>
          ) : null}
        </div>
      ) : null}
      {changes.since && data.status.startsWith("pending") ? (
        <ChangesSummary application={data} changes={changes} labels={labels} />
      ) : null}
      {data.warnings.map((warning) => (
        <p
          key={warning}
          className="flex items-start gap-2 border border-amber-500/30 bg-amber-500/8 px-4 py-2.5 text-sm text-amber-800 dark:text-amber-200"
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {warning}
        </p>
      ))}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_21rem] 2xl:grid-cols-[minmax(0,1fr)_30rem]">
        <DocumentPanel
          documents={documents.data ?? []}
          numbers={numbers}
          application={data}
          fresh={changes.documents}
          first={focused ? mySteps.flatMap((step) => step.documents) : []}
          loading={documents.isPending}
          className="lg:sticky lg:top-18 lg:order-last lg:max-h-[calc(100svh-12rem)] lg:self-start lg:overflow-y-auto lg:pr-1"
        />
        <div className="min-w-0 space-y-3">
          {reviewing ? (
            <StatusTabs
              value={scope}
              onChange={setScope}
              options={[
                { value: "mine", label: "My steps", count: mySteps.filter((step) => step.can_approve).length },
                { value: "all", label: "All steps", count: data.review_steps.length },
              ]}
            />
          ) : null}
          <SectionIndex key={scope} sections={sections} />

          <Card className="p-4">
            <Facts>
              <Fact label="Prepared by">{data.created_by_name}</Fact>
              <Fact label="Submitted by">{data.revisions[0]?.submitted_by_name}</Fact>
              <Fact label="Submission">{data.revision || null}</Fact>
              {data.aadhaar_last4 ? (
                <Fact label="Aadhaar" change={changes.byPath.get("applicant.aadhaar_number")}>
                  <span className="tabular-nums">{numbers.aadhaar}</span>
                </Fact>
              ) : null}
              {data.account_last4 ? (
                <Fact label="Bank account" change={changes.byPath.get("bank.account_number")}>
                  <span className="tabular-nums">{numbers.account}</span>
                </Fact>
              ) : null}
              <Fact label="Animals / surplus">
                {data.computed.total_animals} animals, {data.computed.surplus_lpd} litres a day
              </Fact>
            </Facts>
          </Card>

          {steps.map((step) => (
            <div key={step.key} id={`section-step-${step.key}`} className="scroll-mt-28 space-y-2">
              <div className="flex items-center gap-2 pt-1">
                <h2 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  Step {step.number}: {step.title}
                </h2>
                {step.approved_at ? (
                  <StatusBadge status="approved" label={`Approved by ${step.approved_by_name}`} />
                ) : reviewing ? (
                  <StatusBadge
                    status={step.can_approve ? "pending" : "draft"}
                    label={step.can_approve ? "Your check" : "View only"}
                  />
                ) : null}
              </div>
              {step.sections.map((key) => {
                const section = schema.data.sections.find((item) => item.key === key);
                if (section) return <FormSection key={key} section={section} application={data} changes={changes} />;
                if (key === "place") return <PlaceSection key={key} application={data} />;
                if (key === "family" && family.length) {
                  return <FamilySection key={key} family={family} change={changes.byPath.get("family")} />;
                }
                if (key === "payment") {
                  return (
                    <PaymentCard
                      key={data.payment.deposited_on ?? "new"}
                      application={data}
                      hasProof={hasProof}
                      onChange={refresh}
                    />
                  );
                }
                return null;
              })}
            </div>
          ))}
          <History application={data} />
        </div>
      </div>

      {canAct ? <DecisionBar key={`${data.id}-${data.version}`} application={data} schema={myFields} blocked={blocked} /> : null}
    </div>
  );
}
