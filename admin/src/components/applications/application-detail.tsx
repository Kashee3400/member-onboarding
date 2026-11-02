"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  BadgeCheck,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  CircleX,
  Eye,
  FileDown,
  FileSearch,
  FileText,
  HeartHandshake,
  History as HistoryIcon,
  House,
  IndianRupee,
  Landmark,
  MapPin,
  Milk,
  RotateCcw,
  ScrollText,
  UserRound,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ErrorState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCan } from "@/hooks/use-session";
import { api } from "@/lib/api/client";
import { date, dateTime, humanize, initials } from "@/lib/format";
import { choiceLabel } from "@/lib/form-options";
import type { ApplicationDetail as Application, ApplicationDocument, FormSchema } from "@/lib/types";
import { cn } from "@/lib/utils";

import { changesOf, type Change, type Changes } from "./changes";
import { APPROVE_ALL, STAGE_LABEL, STAGE_PERMISSION, STAGE_QUEUE } from "./constants";
import { CopyButton } from "./copy-button";
import { DecisionBar } from "./decision-bar";
import { StepDocuments } from "./step-documents";
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
  return choiceLabel(value, field.options, field.retired_options);
}

/** Two columns of read-only fields, laid out as the old portal had them. */
function Facts({ children, className }: { children: React.ReactNode; className?: string }) {
  return <dl className={cn("grid gap-x-6 gap-y-4 sm:grid-cols-2", className)}>{children}</dl>;
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
    <div className="min-w-0 space-y-1.5">
      <dt className={cn("text-xs font-medium", flagged ? "text-destructive" : "text-foreground/80")}>
        {label}
        {change ? (
          <span className="ml-1.5 font-medium text-amber-700 dark:text-amber-300">Changed</span>
        ) : null}
      </dt>
      {/* A read-only field: looks like the box it was typed into, and cannot be edited. */}
      <dd
        aria-readonly="true"
        className={cn(
          "flex min-h-9 items-center border bg-muted/50 px-3 py-1.5 text-sm wrap-break-word",
          flagged && "border-destructive/60 bg-destructive/5 font-medium text-destructive",
          change && !flagged && "border-amber-500/60 bg-amber-500/10",
        )}
      >
        {flagged ? <AlertTriangle className="mr-1.5 size-3.5 shrink-0" /> : null}
        {children ?? <span className="text-muted-foreground">—</span>}
      </dd>
      {change ? (
        <p className="text-xs text-muted-foreground">
          Was: <span className="line-through decoration-muted-foreground/50">{change.before || "empty"}</span>
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
  onOpen,
}: {
  application: Application;
  changes: Changes;
  labels: Record<string, string>;
  /** Opens the step a section belongs to. */
  onOpen: (section: string) => void;
}) {
  const rejection = application.decisions
    .filter((item) => item.decision === "rejected" && item.revision === changes.since)
    .at(-1);
  const nothing = !changes.fields.length && !changes.documents.size;
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
                onClick={() => onOpen(change.section)}
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
  const Icon = SECTION_ICONS[id] ?? FileText;
  return (
    <Card id={`section-${id}`} data-section={id} className={cn("scroll-mt-28 gap-4 p-5", className)}>
      <h2 className="flex items-center gap-2.5 text-sm font-semibold">
        <span className="flex size-7 items-center justify-center bg-primary/10 text-primary">
          <Icon className="size-4" />
        </span>
        {title}
      </h2>
      {children}
    </Card>
  );
}

const SECTION_ICONS: Record<string, LucideIcon> = {
  applicant: UserRound,
  address: House,
  location: MapPin,
  animals: Milk,
  bank: Landmark,
  family: Users,
  nominee: HeartHandshake,
  declaration: ScrollText,
  place: MapPin,
  payment: IndianRupee,
  history: HistoryIcon,
};

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
  const fields = section.fields.filter((field) => !(section.key === "animals" && ANIMAL_KEYS.has(field.key)));
  const verified = application.contact_verified;
  return (
    <Section id={section.key} title={section.title}>
      {section.key === "animals" ? <AnimalGrid application={application} /> : null}
      <Facts>
        {/* Older forms have no village of their own, so it comes from the MPP. */}
        {section.key === "address" && values.village_name === undefined ? (
          <Fact label="Village">{application.place.village_name}</Fact>
        ) : null}
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
              {path === "address.mobile" || path === "address.email" ? (
                <Verified at={path === "address.mobile" ? verified.mobile : verified.email} given={!!values[field.key]} />
              ) : null}
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

/** Whether a mobile number or email was confirmed by OTP. */
function Verified({ at, given }: { at: string | null; given: boolean }) {
  if (!given) return null;
  return at ? (
    <span
      className="ml-auto inline-flex shrink-0 items-center gap-1 pl-3 text-xs font-medium text-emerald-700 dark:text-emerald-400"
      title={`Confirmed by OTP on ${dateTime(at)}`}
    >
      <CircleCheck className="size-4" /> Verified
    </span>
  ) : (
    <span
      className="ml-auto inline-flex shrink-0 items-center gap-1 pl-3 text-xs font-medium text-destructive"
      title="Not confirmed by OTP"
    >
      <CircleX className="size-4" /> Not verified
    </span>
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

type Step = Application["review_steps"][number];

/** One tab per step. Each says whether it is done, waiting for this person, or to read. */
function StepTabs({
  steps,
  active,
  onPick,
  reviewing,
  extra,
}: {
  steps: Step[];
  active: string;
  onPick: (key: string) => void;
  reviewing: boolean;
  /** A last tab that is not a step, such as History. */
  extra?: { key: string; label: string };
}) {
  return (
    <nav
      aria-label="Review steps"
      className="sticky top-14 z-10 -mx-1 flex gap-1 overflow-x-auto bg-background/95 px-1 py-1.5 backdrop-blur scrollbar-none"
    >
      {steps.map((step) => {
        const done = !!step.approved_at;
        const yours = reviewing && step.can_approve;
        const current = active === step.key;
        return (
          <button
            key={step.key}
            type="button"
            aria-current={current ? "step" : undefined}
            onClick={() => onPick(step.key)}
            className={cn(
              "flex min-w-36 shrink-0 items-center gap-2.5 border px-3 py-2 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
              current ? "border-primary bg-primary/8 shadow-(--lift)" : "bg-card hover:border-foreground/25",
            )}
          >
            <span
              className={cn(
                "flex size-7 shrink-0 items-center justify-center text-xs font-semibold tabular-nums",
                done
                  ? "bg-emerald-500 text-white"
                  : yours
                    ? "bg-amber-500 text-white"
                    : current
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground",
              )}
            >
              {done ? <Check className="size-4" /> : step.number}
            </span>
            <span className="min-w-0">
              <span className={cn("block truncate text-sm", current && "font-medium")}>{step.title}</span>
              <span
                className={cn(
                  "block text-[11px]",
                  done
                    ? "text-emerald-700 dark:text-emerald-400"
                    : yours
                      ? "text-amber-700 dark:text-amber-300"
                      : "text-muted-foreground",
                )}
              >
                {done ? "Approved" : yours ? "Your check" : "To read"}
              </span>
            </span>
          </button>
        );
      })}
      {extra ? (
        <button
          type="button"
          aria-current={active === extra.key ? "step" : undefined}
          onClick={() => onPick(extra.key)}
          className={cn(
            "flex shrink-0 items-center gap-2 border px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
            active === extra.key ? "border-primary bg-primary/8 font-medium" : "bg-card hover:border-foreground/25",
          )}
        >
          <HistoryIcon className="size-4 text-muted-foreground" /> {extra.label}
        </button>
      ) : null}
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

function FamilySection({
  family,
  lists,
  change,
}: {
  family: NonNullable<Application["data"]["family"]>;
  lists: FormSchema["family"];
  change?: Change;
}) {
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
                <TableCell className="capitalize">
                  {choiceLabel(person.relation, lists?.relations, lists?.retired_relations)}
                </TableCell>
                <TableCell className="capitalize">
                  {choiceLabel(person.gender, lists?.genders, lists?.retired_genders)}
                </TableCell>
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
      <div className="grid gap-4">
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
  const actsOnAll = useCan(APPROVE_ALL);
  const canDecide = useCan(STAGE_PERMISSION[data?.status ?? ""] ?? "") || actsOnAll;
  const canPrintFull = useCan("applications.download_full_pdf");
  const canPayAtFinance =
    (useCan("applications.approve_finance") || actsOnAll) && data?.status === "pending_finance";
  const canPayAtAm = useCan("applications.approve_am") || actsOnAll;
  // Any approver can check the printed form before it is final.
  const canPreview = [canPayAtAm, useCan("applications.approve_cs"), useCan("applications.approve_finance")].some(Boolean);

  const [picked, setPicked] = useState<string | null>(null);
  // Every step, to read, in a dialog: the page itself shows only this person's steps.
  const [viewing, setViewing] = useState<string | null>(null);
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
  const changes = changesOf(data, schema.data, documents.data ?? []);
  const labels: Record<string, string> = Object.fromEntries(
    schema.data.sections.flatMap((section) => section.fields.map((field) => [`${section.key}.${field.key}`, field.label])),
  );

  const mySteps = data.review_steps.filter((step) => step.mine);
  const reviewing = canAct && mySteps.length > 0;
  // Someone who acts on this form sees only their own steps. Anyone else reads them all.
  const tabs = reviewing ? mySteps : data.review_steps;
  const firstOpen = tabs.find((step) => step.can_approve) ?? tabs[0];
  const activeKey =
    picked && (tabs.some((step) => step.key === picked) || (!reviewing && picked === "history"))
      ? picked
      : (firstOpen?.key ?? "history");
  const active = tabs.find((step) => step.key === activeKey) ?? null;
  const position = active ? tabs.indexOf(active) : -1;

  /** After a step is approved, on to the next one this person still has open. */
  const afterApproval = (approved: string) => {
    const open = mySteps.filter((step) => step.can_approve && step.key !== approved);
    const after = open.find((step) => step.number > (active?.number ?? 0)) ?? open[0];
    setPicked(after?.key ?? approved);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  /** A change chip opens its step: here when it is this person's, otherwise in View mode. */
  const openSection = (section: string) => {
    const step = data.review_steps.find((item) => item.sections.includes(section));
    if (!step) return;
    if (tabs.includes(step)) setPicked(step.key);
    else setViewing(step.key);
  };
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
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex size-11 shrink-0 items-center justify-center bg-primary/10 text-base font-semibold text-primary">
              {initials(data.applicant_name || "?")}
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-xl font-semibold tracking-tight">{data.applicant_name || "No name yet"}</h1>
                <StatusBadge status={data.status} label={data.status_label} />
              </div>
              <p className="mt-0.5 text-sm text-muted-foreground">
                <span className="font-mono tabular-nums">{data.form_number || "No form number yet"}</span>
                {" · "}MPP {data.mpp_code} {data.mpp_name}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <FormNav id={data.id} status={data.status} steps={tabs} onStep={setPicked} />
            {reviewing ? (
              <Button
                variant="outline"
                onClick={() => setViewing(active?.key ?? data.review_steps[0].key)}
                title="Read all eight steps of the form"
              >
                <Eye /> View mode
              </Button>
            ) : null}
            {data.status === "approved" ? (
              <>
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
              </>
            ) : stage && canPreview ? (
              <Button
                variant="outline"
                nativeButton={false}
                render={
                  <a
                    href={`/api/backend/applications/${id}/preview-pdf?variant=${canPrintFull ? "full" : "single"}`}
                    target="_blank"
                    rel="noreferrer"
                    title="The form as it would print if approved now. Marked as a draft and not kept."
                  />
                }
              >
                <FileSearch /> Preview PDF
              </Button>
            ) : null}
          </div>
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
        <ChangesSummary application={data} changes={changes} labels={labels} onOpen={openSection} />
      ) : null}
      {data.warnings.map((warning) => (
        <p
          key={warning}
          className="flex items-start gap-2 border border-amber-500/30 bg-amber-500/8 px-4 py-2.5 text-sm text-amber-800 dark:text-amber-200"
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {warning}
        </p>
      ))}

      <div>
        <div className="min-w-0 space-y-3">
          <StepTabs
            steps={tabs}
            active={activeKey}
            onPick={setPicked}
            reviewing={reviewing}
            extra={reviewing ? undefined : { key: "history", label: "History" }}
          />

          {active ? (
            <div key={active.key} className="space-y-3 motion-safe:animate-in motion-safe:fade-in motion-safe:duration-200">
              <StepContent
                step={active}
                application={data}
                schema={schema.data}
                changes={changes}
                documents={documents.data ?? []}
                numbers={numbers}
                status={
                  active.approved_at
                    ? "approved"
                    : reviewing && active.can_approve
                      ? "yours"
                      : "read"
                }
                payment={
                  hasPayment ? (
                    <PaymentCard
                      key={data.payment.deposited_on ?? "new"}
                      application={data}
                      hasProof={hasProof}
                      onChange={refresh}
                    />
                  ) : null
                }
              />
              <div className="flex items-center justify-between gap-2">
                <Button
                  variant="ghost"
                  disabled={position <= 0}
                  onClick={() => setPicked(tabs[position - 1]?.key ?? null)}
                >
                  <ChevronLeft /> {position > 0 ? tabs[position - 1].title : "Previous"}
                </Button>
                <Button
                  variant="ghost"
                  disabled={position >= tabs.length - 1}
                  onClick={() => setPicked(tabs[position + 1]?.key ?? null)}
                >
                  {position < tabs.length - 1 ? tabs[position + 1].title : "Next"} <ChevronRight />
                </Button>
              </div>
            </div>
          ) : (
            <History application={data} />
          )}
        </div>
      </div>

      {canAct ? (
        <DecisionBar
          key={`${data.id}-${data.version}`}
          application={data}
          schema={myFields}
          blocked={blocked}
          current={reviewing ? active : null}
          onApproved={afterApproval}
        />
      ) : null}

      <AllStepsDialog
        open={viewing !== null}
        onOpenChange={(open) => setViewing(open ? viewing : null)}
        active={viewing}
        onPick={setViewing}
        application={data}
        schema={schema.data}
        changes={changes}
        documents={documents.data ?? []}
        numbers={numbers}
      />
    </div>
  );
}

/** One step's sections, and whether it is done, waiting for this person, or to read. */
function StepContent({
  step,
  application,
  schema,
  changes,
  status,
  payment,
  documents,
  numbers,
  inDialog = false,
}: {
  step: Step;
  application: Application;
  schema: FormSchema;
  changes: Changes;
  status: "approved" | "yours" | "read";
  /** How the payment shows: editable on the page, read-only in View mode. */
  payment: React.ReactNode;
  documents: ApplicationDocument[];
  numbers: ReturnType<typeof useSensitiveNumbers>;
  inDialog?: boolean;
}) {
  const family = application.data.family ?? [];
  // The numbers the old portal showed inside the step, to check against the photos below.
  const extra =
    step.key === "member" ? (
      <Card className="gap-4 p-5">
        <Facts>
          <Fact label="Form No.">
            <span className="font-mono tabular-nums">{application.form_number || "—"}</span>
          </Fact>
          <Fact label="Aadhaar card No." change={changes.byPath.get("applicant.aadhaar_number")}>
            <span className="font-mono tabular-nums">{numbers.aadhaar || null}</span>
          </Fact>
        </Facts>
      </Card>
    ) : step.key === "bank" ? (
      <Card className="gap-4 p-5">
        <Facts>
          <Fact label="Account number" change={changes.byPath.get("bank.account_number")}>
            <span className="font-mono tabular-nums">{numbers.account || null}</span>
          </Fact>
        </Facts>
      </Card>
    ) : null;
  const parts = step.sections
    .map((key) => {
      const section = schema.sections.find((item) => item.key === key);
      if (section) return <FormSection key={key} section={section} application={application} changes={changes} />;
      if (key === "place") return <PlaceSection key={key} application={application} />;
      if (key === "family" && family.length) {
        return (
          <FamilySection key={key} family={family} lists={schema.family} change={changes.byPath.get("family")} />
        );
      }
      if (key === "payment" && payment) return <div key={key}>{payment}</div>;
      return null;
    })
    .filter(Boolean);
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">
          <span className="text-muted-foreground">Step {step.number} of 8 · </span>
          {step.title}
        </h2>
        {status === "approved" ? (
          <StatusBadge status="approved" label={`Approved by ${step.approved_by_name}`} />
        ) : status === "yours" ? (
          <StatusBadge status="pending" label="Waiting for your check" />
        ) : (
          <StatusBadge status="draft" label={step.approved_at ? "Approved" : "Not approved yet"} />
        )}
      </div>
      {extra}
      {parts.length ? parts : <Card className="p-5 text-sm text-muted-foreground">Nothing was filled in for this step.</Card>}
      {step.documents.length ? (
        <StepDocuments
          types={step.documents}
          documents={documents}
          numbers={numbers}
          application={application}
          floats={!inDialog}
        />
      ) : null}
    </>
  );
}

/** The payment as recorded, for reading. Recording it happens on the form page. */
function PaymentFacts({ application }: { application: Application }) {
  const paid = application.payment;
  if (!paid.amount) {
    return <Card className="p-5 text-sm text-muted-foreground">No payment recorded yet.</Card>;
  }
  return (
    <Section id="payment" title="Member fee">
      <Facts>
        <Fact label="Amount">{`₹ ${paid.amount}`}</Fact>
        <Fact label="Deposited on">{paid.deposited_on ? date(paid.deposited_on) : null}</Fact>
        <Fact label="Mode">{paid.mode ? humanize(paid.mode) : null}</Fact>
        <Fact label="Bank">{paid.bank_name || null}</Fact>
        <Fact label="Reference">{paid.reference || null}</Fact>
        <Fact label="Recorded by">{paid.recorded_by_name || null}</Fact>
      </Facts>
    </Section>
  );
}

/** View mode: all eight steps and the history, one tab each, to read only. */
function AllStepsDialog({
  open,
  onOpenChange,
  active,
  onPick,
  application,
  schema,
  changes,
  documents,
  numbers,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  active: string | null;
  onPick: (key: string) => void;
  application: Application;
  schema: FormSchema;
  changes: Changes;
  documents: ApplicationDocument[];
  numbers: ReturnType<typeof useSensitiveNumbers>;
}) {
  const step = application.review_steps.find((item) => item.key === active) ?? null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[88svh] flex-col gap-3 p-0 sm:max-w-6xl">
        <DialogHeader className="shrink-0 border-b px-5 pt-5 pb-3">
          <DialogTitle className="flex items-center gap-2">
            <Eye className="size-4" /> {application.applicant_name}: all steps
          </DialogTitle>
          <DialogDescription>For reading only. Approving is done on the form page, step by step.</DialogDescription>
        </DialogHeader>
        <div className="shrink-0 px-5">
          <StepTabs
            steps={application.review_steps}
            active={active ?? ""}
            onPick={onPick}
            reviewing={false}
            extra={{ key: "history", label: "History" }}
          />
        </div>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-5 pb-5">
          {step ? (
            <StepContent
              key={step.key}
              step={step}
              application={application}
              schema={schema}
              changes={changes}
              documents={documents}
              numbers={numbers}
              inDialog
              status={step.approved_at ? "approved" : "read"}
              payment={<PaymentFacts application={application} />}
            />
          ) : (
            <History application={application} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
