"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Info, Send } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { FormError, messageOf } from "@/components/admin/feedback";
import { SaveBar, SettingsCard, SettingsNav, useUnsavedGuard } from "@/components/admin/settings-form";
import { Field } from "@/components/common/field";
import { SecretInput } from "@/components/common/form-input";
import { PageHeader } from "@/components/common/page-header";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api/client";
import type { Integration } from "@/lib/types";

type FieldSpec = { name: string; label: string; type?: "number" | "boolean" | "long"; help?: string };
type Spec = { title: string; hint: string; config: FieldSpec[]; secrets: FieldSpec[]; note?: string };

const SPECS: Record<string, Spec> = {
  mail: {
    title: "Mail",
    hint: "Password resets and notices",
    config: [
      { name: "host", label: "SMTP host" },
      { name: "port", label: "Port", type: "number" },
      { name: "username", label: "Username" },
      { name: "from_email", label: "From address" },
      { name: "use_tls", label: "Use TLS", type: "boolean", help: "Keep this on unless your mail provider says otherwise." },
    ],
    secrets: [{ name: "password", label: "Password" }],
  },
  sms: {
    title: "SMS",
    hint: "OTPs to members' mobile numbers",
    note: "Use the same gateway account as the ERP. The OTP message must be the exact DLT-approved text for its template, with {otp} where the code goes.",
    config: [
      { name: "provider", label: "Provider", help: "A name for your own reference." },
      { name: "base_url", label: "Gateway URL", help: "The address the ERP sends its SMS to." },
      { name: "user_id", label: "User ID" },
      { name: "sender_id", label: "Sender ID" },
      { name: "dlt_entity_id", label: "DLT entity ID" },
      { name: "otp_template_id", label: "DLT template ID for the OTP" },
      {
        name: "otp_message",
        label: "OTP message",
        type: "long",
        help: "Exactly as approved on DLT. {otp} is replaced by the code.",
      },
    ],
    secrets: [{ name: "password", label: "Password" }],
  },
  whatsapp: {
    title: "WhatsApp",
    hint: "WhatsApp messages",
    note: "These details are saved for later. The portal does not send WhatsApp messages yet.",
    config: [
      { name: "provider", label: "Provider" },
      { name: "base_url", label: "Base URL" },
      { name: "phone_number_id", label: "Phone number ID" },
    ],
    secrets: [{ name: "api_key", label: "API key" }],
  },
};

type Values = Record<string, string | boolean>;

function startingValues(integration: Integration, spec: Spec): Values {
  return Object.fromEntries(
    spec.config.map((field) => [
      field.name,
      field.type === "boolean"
        ? Boolean(integration.config[field.name])
        : String(integration.config[field.name] ?? ""),
    ]),
  );
}

function IntegrationForm({
  integration,
  spec,
  onDirty,
}: {
  integration: Integration;
  spec: Spec;
  onDirty: (dirty: boolean) => void;
}) {
  const client = useQueryClient();
  const start = startingValues(integration, spec);
  const [enabled, setEnabled] = useState(integration.is_enabled);
  const [values, setValues] = useState(start);
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const dirty =
    enabled !== integration.is_enabled ||
    JSON.stringify(values) !== JSON.stringify(start) ||
    Object.values(secrets).some(Boolean);

  useEffect(() => onDirty(dirty), [dirty, onDirty]);

  const save = useMutation({
    mutationFn: (body: object) => api(`settings/integrations/${integration.kind}`, { method: "PUT", body }),
    onSuccess: () => {
      setSecrets({});
      toast.success(`${spec.title} saved.`);
      client.invalidateQueries({ queryKey: ["integrations"] });
    },
  });
  const test = useMutation({
    mutationFn: () => api("settings/integrations/mail/test", { method: "POST" }),
    onSuccess: () => toast.success("Test mail sent to you. Check your inbox."),
    onError: (error) => toast.error(messageOf(error)),
  });
  const [testMobile, setTestMobile] = useState("");
  const testSms = useMutation({
    mutationFn: () => api("settings/integrations/sms/test", { method: "POST", body: { mobile: testMobile } }),
    onSuccess: () => toast.success("Test SMS sent with the code 123456. Check the phone."),
    onError: (error) => toast.error(messageOf(error)),
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const config: Record<string, unknown> = {};
    for (const field of spec.config) {
      const value = values[field.name];
      if (field.type === "boolean") config[field.name] = value;
      else if (value) config[field.name] = field.type === "number" ? Number(value) : value;
    }
    // Left blank means keep what is stored: saved secrets are never sent back here.
    save.mutate({
      is_enabled: enabled,
      config,
      secrets: Object.fromEntries(Object.entries(secrets).filter(([, value]) => value)),
    });
  };

  const discard = () => {
    setEnabled(integration.is_enabled);
    setValues(start);
    setSecrets({});
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <SettingsCard
        title={spec.title}
        description={spec.hint}
        aside={<StatusBadge status={integration.is_enabled ? "active" : "draft"} label={integration.is_enabled ? "On" : "Off"} />}
      >
        <div className="space-y-4">
          {spec.note ? (
            <Alert>
              <Info />
              <AlertDescription>{spec.note}</AlertDescription>
            </Alert>
          ) : null}
          <label className="flex items-center justify-between gap-3 text-sm">
            <span>
              <span className="block font-medium">Turn on {spec.title}</span>
              <span className="block text-xs text-muted-foreground">Off keeps the details but stops using them.</span>
            </span>
            <Switch checked={enabled} onCheckedChange={(on) => setEnabled(Boolean(on))} />
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            {spec.config.map((field) =>
              field.type === "boolean" ? (
                <label key={field.name} className="flex items-center justify-between gap-3 text-sm sm:col-span-2">
                  <span>
                    <span className="block font-medium">{field.label}</span>
                    {field.help ? <span className="block text-xs text-muted-foreground">{field.help}</span> : null}
                  </span>
                  <Switch
                    checked={Boolean(values[field.name])}
                    onCheckedChange={(on) => setValues({ ...values, [field.name]: Boolean(on) })}
                  />
                </label>
              ) : (
                <Field
                  key={field.name}
                  label={field.label}
                  htmlFor={field.name}
                  help={field.help}
                  className={field.type === "long" ? "sm:col-span-2" : undefined}
                >
                  {field.type === "long" ? (
                    <Textarea
                      id={field.name}
                      rows={3}
                      value={String(values[field.name])}
                      onChange={(event) => setValues({ ...values, [field.name]: event.target.value })}
                    />
                  ) : (
                    <Input
                      id={field.name}
                      type={field.type ?? "text"}
                      value={String(values[field.name])}
                      onChange={(event) => setValues({ ...values, [field.name]: event.target.value })}
                    />
                  )}
                </Field>
              ),
            )}
            {spec.secrets.map((field) => {
              const isSet = integration.configured_secrets.includes(field.name);
              return (
                <Field
                  key={field.name}
                  label={field.label}
                  htmlFor={field.name}
                  help={isSet ? "Saved. Leave blank to keep it." : "Stored encrypted, and never shown again."}
                >
                  <SecretInput
                    id={field.name}
                    autoComplete="new-password"
                    placeholder={isSet ? "••••••••" : ""}
                    value={secrets[field.name] ?? ""}
                    onChange={(event) => setSecrets({ ...secrets, [field.name]: event.target.value })}
                  />
                </Field>
              );
            })}
          </div>
          <FormError error={save.error} />
          {integration.kind === "mail" ? (
            <div className="border-t pt-3">
              <Button
                type="button"
                variant="outline"
                disabled={test.isPending || !integration.is_enabled || dirty}
                onClick={() => test.mutate()}
              >
                <Send /> {test.isPending ? "Sending…" : "Send test mail"}
              </Button>
              <p className="mt-1.5 text-xs text-muted-foreground">
                {dirty ? "Save first, then test." : integration.is_enabled ? "Goes to your own address." : "Turn mail on and save first."}
              </p>
            </div>
          ) : null}
          {integration.kind === "sms" ? (
            <div className="space-y-1.5 border-t pt-3">
              <div className="flex flex-wrap items-end gap-2">
                <Field label="Send a test to" htmlFor="sms-test-mobile" className="min-w-48 flex-1">
                  <Input
                    id="sms-test-mobile"
                    inputMode="numeric"
                    maxLength={10}
                    placeholder="10-digit mobile number"
                    value={testMobile}
                    onChange={(event) => setTestMobile(event.target.value.replace(/\D/g, ""))}
                  />
                </Field>
                <Button
                  type="button"
                  variant="outline"
                  disabled={testSms.isPending || !integration.is_enabled || dirty || testMobile.length !== 10}
                  onClick={() => testSms.mutate()}
                >
                  <Send /> {testSms.isPending ? "Sending…" : "Send test SMS"}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                {dirty
                  ? "Save first, then test."
                  : integration.is_enabled
                    ? "Sends the OTP message with the code 123456."
                    : "Turn SMS on and save first."}
              </p>
            </div>
          ) : null}
        </div>
      </SettingsCard>
      <SaveBar dirty={dirty} saving={save.isPending} onDiscard={discard} />
    </form>
  );
}

export default function IntegrationsPage() {
  const integrations = useQuery({
    queryKey: ["integrations"],
    queryFn: () => api<Integration[]>("settings/integrations"),
  });
  const [kind, setKind] = useState("mail");
  const [dirty, setDirty] = useState(false);
  const { guard, dialog } = useUnsavedGuard(dirty);

  const list = (integrations.data ?? []).filter((item) => SPECS[item.kind]);
  const current = list.find((item) => item.kind === kind);

  return (
    <>
      <PageHeader
        title="Integrations"
        description="Outside services this organization uses, changeable without a deployment."
      />
      {integrations.isPending ? <ListSkeleton /> : null}
      {integrations.error ? <ErrorState error={integrations.error} onRetry={() => integrations.refetch()} /> : null}
      {current ? (
        <div className="grid gap-4 lg:grid-cols-[14rem_minmax(0,1fr)]">
          <SettingsNav
            value={kind}
            onChange={(next) =>
              guard(() => {
                setDirty(false);
                setKind(next);
              })
            }
            sections={list.map((item) => ({
              key: item.kind,
              label: SPECS[item.kind].title,
              hint: SPECS[item.kind].hint,
              status: (
                <span
                  className={`size-2 rounded-full ${item.is_enabled ? "bg-emerald-500" : "bg-muted-foreground/30"}`}
                  title={item.is_enabled ? "On" : "Off"}
                />
              ),
            }))}
          />
          <IntegrationForm
            key={`${current.kind}-${JSON.stringify(current)}`}
            integration={current}
            spec={SPECS[current.kind]}
            onDirty={setDirty}
          />
        </div>
      ) : null}
      {dialog}
    </>
  );
}
