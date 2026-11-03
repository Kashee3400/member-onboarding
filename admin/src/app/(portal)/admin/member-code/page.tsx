"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { FormError } from "@/components/admin/feedback";
import {
  SaveBar,
  SettingsCard,
  SettingsNav,
  useUnsavedGuard,
} from "@/components/admin/settings-form";
import { DatePicker } from "@/components/common/date-picker";
import { Field } from "@/components/common/field";
import { PageHeader } from "@/components/common/page-header";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api/client";
import { rupees } from "@/lib/format";
import type { MemberCodeSettings, OrganizationProfile } from "@/lib/types";

const EXAMPLE_VILLAGE = "00209982";

function CodeAnatomy({
  state_code,
  hamlet_code,
}: {
  state_code: string;
  hamlet_code: string;
}) {
  const parts = [
    { value: state_code.padEnd(2, "–"), label: "State code", live: true },
    { value: EXAMPLE_VILLAGE, label: "Village code", live: false },
    { value: hamlet_code.padEnd(2, "–"), label: "Hamlet code", live: true },
    { value: "0001", label: "Serial", live: false },
  ];
  return (
    <div className="overflow-x-auto">
      <div className="flex w-fit divide-x border font-mono text-sm tabular-nums">
        {parts.map((part) => (
          <div key={part.label} className="px-3 py-2 text-center">
            <div className={part.live ? "font-semibold text-primary" : ""}>
              {part.value}
            </div>
            <div className="font-sans text-[11px] whitespace-nowrap text-muted-foreground">
              {part.label}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CodeForm({
  value,
  onDirty,
}: {
  value: MemberCodeSettings;
  onDirty: (dirty: boolean) => void;
}) {
  const client = useQueryClient();
  const [form, setForm] = useState(value);
  const dirty = JSON.stringify(form) !== JSON.stringify(value);
  useEffect(() => onDirty(dirty), [dirty, onDirty]);

  const set = <K extends keyof MemberCodeSettings>(
    key: K,
    next: MemberCodeSettings[K],
  ) => setForm({ ...form, [key]: next });

  const save = useMutation({
    mutationFn: (body: object) =>
      api<MemberCodeSettings>("settings/member-code", { method: "PUT", body }),
    onSuccess: (saved) => {
      client.setQueryData(["member-code"], saved);
      toast.success("Member code settings saved.");
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    save.mutate(form);
  };

  const number = (key: "entry_fee" | "share_price" | "share_count") => ({
    id: key,
    type: "number",
    min: 0,
    required: true,
    value: form[key],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      set(key, Number(event.target.value)),
  });

  return (
    <form onSubmit={submit} className="space-y-4">
      <SettingsCard
        title="Member code"
        description="16 digits, given when Finance gives the final approval."
      >
        <div className="space-y-4">
          <CodeAnatomy
            state_code={form.state_code}
            hamlet_code={form.hamlet_code}
          />
          <div className="grid gap-4 sm:grid-cols-3">
            <Field
              label="Default state code"
              htmlFor="state_code"
              help="Used only for an MPP with no state code of its own."
            >
              <Input
                id="state_code"
                required
                pattern="\d{2}"
                maxLength={2}
                inputMode="numeric"
                className="font-mono"
                value={form.state_code}
                onChange={(event) => set("state_code", event.target.value)}
              />
            </Field>
            <Field
              label="Default hamlet code"
              htmlFor="hamlet_code"
              help="Used only for an MPP with no hamlet code of its own."
            >
              <Input
                id="hamlet_code"
                required
                pattern="\d{2}"
                maxLength={2}
                inputMode="numeric"
                className="font-mono"
                value={form.hamlet_code}
                onChange={(event) => set("hamlet_code", event.target.value)}
              />
            </Field>
            <Field
              label="Form number prefix"
              htmlFor="form_prefix"
              help="For example A in A00012."
            >
              <Input
                id="form_prefix"
                required
                maxLength={4}
                className="font-mono"
                value={form.form_prefix}
                onChange={(event) => set("form_prefix", event.target.value)}
              />
            </Field>
          </div>
        </div>
      </SettingsCard>

      <SettingsCard
        title="Fees"
        description="Printed on the form and used when Finance records payment."
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Entry fee (₹)" htmlFor="entry_fee">
            <Input {...number("entry_fee")} />
          </Field>
          <Field label="Share price (₹)" htmlFor="share_price">
            <Input {...number("share_price")} />
          </Field>
          <Field label="Shares per member" htmlFor="share_count">
            <Input {...number("share_count")} />
          </Field>
        </div>
        <p className="mt-3 text-sm text-muted-foreground">
          Entry fee plus shares:{" "}
          <span className="font-medium text-foreground tabular-nums">
            {rupees(form.entry_fee + form.share_price * form.share_count)}
          </span>
        </p>
      </SettingsCard>

      <FormError error={save.error} />
      <SaveBar
        dirty={dirty}
        saving={save.isPending}
        onDiscard={() => setForm(value)}
      />
    </form>
  );
}

const PROFILE_GROUPS: {
  title: string;
  description?: string;
  fields: { name: keyof OrganizationProfile; label: string; type?: string }[];
}[] = [
  {
    title: "Company",
    description: "As it appears at the top of the form.",
    fields: [
      { name: "company_name_hi", label: "Name for the heading (Hindi)" },
      { name: "company_name_hi_short", label: "Name in the text (Hindi)" },
      { name: "cin", label: "CIN" },
    ],
  },
  {
    title: "Registered office",
    fields: [
      { name: "address_line_1", label: "Line 1" },
      { name: "address_line_2", label: "Line 2" },
      { name: "phone", label: "Phone" },
      { name: "email", label: "Email", type: "email" },
      { name: "website", label: "Website" },
    ],
  },
  {
    title: "Letter and signing",
    fields: [
      { name: "city_hi", label: "Addressed to (Hindi)" },
      { name: "city_short_hi", label: "City (Hindi)" },
      { name: "place", label: "Place of signing" },
      { name: "board_resolution_no", label: "Board resolution number" },
    ],
  },
];

function ProfileForm({
  value,
  onDirty,
}: {
  value: OrganizationProfile;
  onDirty: (dirty: boolean) => void;
}) {
  const client = useQueryClient();
  const [form, setForm] = useState(value);
  const dirty = JSON.stringify(form) !== JSON.stringify(value);
  useEffect(() => onDirty(dirty), [dirty, onDirty]);

  const save = useMutation({
    mutationFn: (body: object) =>
      api<OrganizationProfile>("settings/organization-profile", {
        method: "PUT",
        body,
      }),
    onSuccess: (saved) => {
      client.setQueryData(["organization-profile"], saved);
      toast.success("Printed form details saved.");
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    save.mutate({
      ...form,
      board_resolution_date: form.board_resolution_date || null,
    });
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      {PROFILE_GROUPS.map((group) => (
        <SettingsCard
          key={group.title}
          title={group.title}
          description={group.description}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            {group.fields.map((field) => (
              <Field key={field.name} label={field.label} htmlFor={field.name}>
                <Input
                  id={field.name}
                  type={field.type ?? "text"}
                  value={String(form[field.name] ?? "")}
                  onChange={(event) =>
                    setForm({ ...form, [field.name]: event.target.value })
                  }
                />
              </Field>
            ))}
            {group.title === "Letter and signing" ? (
              <Field label="Board resolution date">
                <DatePicker
                  aria-label="Board resolution date"
                  value={form.board_resolution_date}
                  onChange={(date) =>
                    setForm({ ...form, board_resolution_date: date || null })
                  }
                />
              </Field>
            ) : null}
          </div>
        </SettingsCard>
      ))}
      <SettingsCard title="Who can join">
        <label className="flex items-center justify-between gap-3 text-sm">
          <span>
            <span className="block font-medium">
              Membership is open to women only
            </span>
            <span className="block text-xs text-muted-foreground">
              The form then uses female wording only.
            </span>
          </span>
          <Switch
            checked={form.members_female_only}
            onCheckedChange={(on) =>
              setForm({ ...form, members_female_only: Boolean(on) })
            }
          />
        </label>
      </SettingsCard>
      <SettingsCard title="Privacy">
        <Field
          label="Discard unsubmitted drafts after"
          htmlFor="draft-retention"
          help="Days without a change. The draft and its Aadhaar and bank photos are deleted. 0 keeps drafts."
        >
          <div className="flex items-center gap-2">
            <Input
              id="draft-retention"
              type="number"
              min={0}
              max={3650}
              className="w-28 tabular-nums"
              value={form.draft_retention_days}
              onChange={(event) =>
                setForm({
                  ...form,
                  draft_retention_days: Number(event.target.value),
                })
              }
            />
            <span className="text-sm text-muted-foreground">days</span>
          </div>
        </Field>
      </SettingsCard>
      <FormError error={save.error} />
      <SaveBar
        dirty={dirty}
        saving={save.isPending}
        onDiscard={() => setForm(value)}
      />
    </form>
  );
}

const SECTIONS = [
  {
    key: "code",
    label: "Code and fees",
    hint: "Member code, form number, fees",
  },
  {
    key: "profile",
    label: "Printed form details",
    hint: "Company details on the PDF",
  },
];

export default function MemberCodePage() {
  const settings = useQuery({
    queryKey: ["member-code"],
    queryFn: () => api<MemberCodeSettings>("settings/member-code"),
  });
  const profile = useQuery({
    queryKey: ["organization-profile"],
    queryFn: () => api<OrganizationProfile>("settings/organization-profile"),
  });
  const [section, setSection] = useState("code");
  const [dirty, setDirty] = useState(false);
  const { guard, dialog } = useUnsavedGuard(dirty);
  const failed = settings.error ?? profile.error;

  return (
    <>
      <PageHeader
        title="Member Code"
        description="How member codes are built, and what the printed form says."
      />
      {failed ? (
        <ErrorState
          error={failed}
          onRetry={() =>
            settings.error ? settings.refetch() : profile.refetch()
          }
        />
      ) : !settings.data || !profile.data ? (
        <ListSkeleton />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[14rem_minmax(0,1fr)]">
          <SettingsNav
            sections={SECTIONS}
            value={section}
            onChange={(next) =>
              guard(() => {
                setDirty(false);
                setSection(next);
              })
            }
          />
          {section === "code" ? (
            <CodeForm
              key={JSON.stringify(settings.data)}
              value={settings.data}
              onDirty={setDirty}
            />
          ) : (
            <ProfileForm
              key={JSON.stringify(profile.data)}
              value={profile.data}
              onDirty={setDirty}
            />
          )}
        </div>
      )}
      {dialog}
    </>
  );
}
