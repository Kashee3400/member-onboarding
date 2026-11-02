"use client";

import { Building2, Check, Copy, Download, KeyRound, Lock, ShieldCheck, Smartphone } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { QRCodeSVG } from "qrcode.react";
import { type FormEvent, useState } from "react";
import { toast } from "sonner";

import { Field } from "@/components/common/field";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { auth, reloadTo } from "@/lib/api";
import type { Branding } from "@/lib/branding-types";

import { AuthCard, AuthFrame, type TrustBadge } from "./auth-frame";
import { CodeBoxes, EmailField, IconField, InfoNote, LINK_CLASS, PasswordField, ProblemNote, SUBMIT_CLASS } from "./fields";

type Step =
  | { name: "password" }
  | { name: "verify" }
  | { name: "enroll"; secret: string; uri: string }
  | { name: "recovery"; codes: string[] };

const PANEL: Record<Step["name"], { headline: string; message: string; badges?: TrustBadge[] }> = {
  password: {
    headline: "Every member,\nproperly onboarded",
    message: "Forms, approvals and member codes in one place, for your staff only.",
  },
  verify: {
    headline: "Verify\nyour identity",
    message: "One more step. The code from your phone confirms it is really you.",
    badges: [
      { icon: ShieldCheck, label: "Identity check" },
      { icon: Smartphone, label: "Authenticator app" },
    ],
  },
  enroll: {
    headline: "Protect\nyour account",
    message: "Your role handles member records, so it needs a code from your phone at each sign-in.",
    badges: [
      { icon: Smartphone, label: "Set up once" },
      { icon: Lock, label: "Always protected" },
    ],
  },
  recovery: {
    headline: "Keep your\nrecovery codes",
    message: "They are your way back in if you ever lose your phone.",
    badges: [
      { icon: KeyRound, label: "Emergency access" },
      { icon: Lock, label: "One-time use" },
    ],
  },
};

/** Only paths inside the portal, never an outside address. */
function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/";
  return raw;
}

const clip = (text: string) =>
  navigator.clipboard.writeText(text).then(
    () => toast.success("Copied"),
    () => toast.error("This browser would not copy it. Select the text instead."),
  );

export function LoginFlow({ branding, organization }: { branding: Branding; organization: string }) {
  const query = useSearchParams();
  const next = safeNext(query.get("next"));
  const expired = !!query.get("expired");

  const [step, setStep] = useState<Step>({ name: "password" });
  const [problem, setProblem] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const [org, setOrg] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const [saved, setSaved] = useState(false);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setProblem(null);
    try {
      await action();
    } catch (failure) {
      setProblem(failure);
      setCode("");
    } finally {
      setBusy(false);
    }
  }

  function signIn(event: FormEvent) {
    event.preventDefault();
    const slug = organization || org.trim();
    if (!slug || !email.trim() || !password) {
      setProblem(`Enter your ${!slug ? "organization" : !email.trim() ? "email" : "password"} to continue.`);
      return;
    }
    run(async () => {
      const result = await auth("login", { email: email.trim(), password, organization: slug });
      setPassword("");
      if (result.status === "ok") {
        reloadTo(next);
      } else if (result.status === "verify") {
        setStep({ name: "verify" });
      } else {
        const enrollment = await auth("mfa/enroll");
        setStep({ name: "enroll", secret: enrollment.secret!, uri: enrollment.otpauth_uri! });
      }
    });
  }

  function verify(value: string) {
    if (busy) return;
    run(async () => {
      await auth("mfa/verify", useRecovery ? { recovery_code: value.trim() } : { code: value });
      reloadTo(next);
    });
  }

  function confirm(value: string) {
    if (busy) return;
    run(async () => {
      const result = await auth("mfa/confirm", { code: value });
      setStep({ name: "recovery", codes: result.recovery_codes! });
    });
  }

  function startOver() {
    setProblem(null);
    setCode("");
    setRecovery("");
    setUseRecovery(false);
    setStep({ name: "password" });
  }

  function download(codes: string[]) {
    const url = URL.createObjectURL(
      new Blob([`${branding.display_name} recovery codes for ${email.trim()}\n\n${codes.join("\n")}\n`], {
        type: "text/plain",
      }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "recovery-codes.txt";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <AuthFrame branding={branding} {...PANEL[step.name]}>
      {step.name === "password" ? (
        <AuthCard
          step={1}
          title={`Sign in to ${branding.display_name}`}
          description="Staff only. Use the email your organization gave you."
        >
          <form noValidate onSubmit={signIn} className="space-y-4">
            {expired && !problem ? <InfoNote>Your session ended. Sign in again to continue.</InfoNote> : null}
            <ProblemNote problem={problem} />
            {organization ? null : (
              <IconField
                id="organization"
                label="Organization"
                icon={Building2}
                autoComplete="organization"
                autoFocus
                value={org}
                onChange={(event) => setOrg(event.target.value)}
              />
            )}
            <EmailField autoFocus={!!organization} value={email} onChange={(event) => setEmail(event.target.value)} />
            <PasswordField
              id="password"
              label="Password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <Button type="submit" disabled={busy} className={SUBMIT_CLASS}>
              {busy ? "Checking…" : "Continue"}
            </Button>
            <p className="text-center">
              <Link href="/forgot-password" className={LINK_CLASS}>
                Forgot your password?
              </Link>
            </p>
          </form>
        </AuthCard>
      ) : null}

      {step.name === "verify" ? (
        <AuthCard
          step={2}
          title="Two-step verification"
          description={
            useRecovery
              ? "Enter one of the recovery codes you saved. Each works once."
              : "Enter the 6-digit code from your authenticator app."
          }
        >
          <form
            noValidate
            onSubmit={(event) => {
              event.preventDefault();
              verify(useRecovery ? recovery : code);
            }}
            className="space-y-4"
          >
            <ProblemNote problem={problem} />
            {useRecovery ? (
              <IconField
                id="recovery"
                label="Recovery code"
                icon={KeyRound}
                autoFocus
                autoComplete="one-time-code"
                value={recovery}
                onChange={(event) => setRecovery(event.target.value)}
              />
            ) : (
              <CodeBoxes label="Authenticator code" value={code} onChange={setCode} onComplete={verify} invalid={!!problem} />
            )}
            <Button
              type="submit"
              disabled={busy || (useRecovery ? !recovery.trim() : code.length !== 6)}
              className={SUBMIT_CLASS}
            >
              <ShieldCheck className="size-4" />
              {busy ? "Verifying…" : "Verify and sign in"}
            </Button>
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
              <button
                type="button"
                className={LINK_CLASS}
                onClick={() => {
                  setProblem(null);
                  setCode("");
                  setRecovery("");
                  setUseRecovery(!useRecovery);
                }}
              >
                {useRecovery ? "Use authenticator code" : "Lost your phone?"}
              </button>
              <button type="button" className={LINK_CLASS} onClick={startOver}>
                Start over
              </button>
            </div>
          </form>
        </AuthCard>
      ) : null}

      {step.name === "enroll" ? (
        <AuthCard
          step={2}
          title="Set up your authenticator"
          description="Scan this with Microsoft or Google Authenticator, then enter the code it shows."
        >
          <form
            noValidate
            onSubmit={(event) => {
              event.preventDefault();
              confirm(code);
            }}
            className="space-y-4"
          >
            <ProblemNote problem={problem} />
            <div className="flex items-center gap-4 border bg-muted/40 p-3">
              {/* Always black on white: phones can't read it otherwise. */}
              <div className="shrink-0 bg-white p-2">
                <QRCodeSVG value={step.uri} size={112} level="M" />
              </div>
              <div className="min-w-0 space-y-1.5">
                <p className="text-xs text-muted-foreground">Can&apos;t scan? Enter this key by hand.</p>
                <code className="block font-mono text-xs leading-relaxed tracking-wider break-all">
                  {step.secret.match(/.{1,4}/g)?.join(" ")}
                </code>
                <Button type="button" variant="outline" size="xs" onClick={() => clip(step.secret)}>
                  <Copy className="size-3" /> Copy key
                </Button>
              </div>
            </div>
            <Field label="Code from the app">
              <CodeBoxes label="Code from the app" value={code} onChange={setCode} onComplete={confirm} invalid={!!problem} />
            </Field>
            <Button type="submit" disabled={busy || code.length !== 6} className={SUBMIT_CLASS}>
              {busy ? "Confirming…" : "Confirm and continue"}
            </Button>
            <p className="text-center">
              <button type="button" className={LINK_CLASS} onClick={startOver}>
                Start over
              </button>
            </p>
          </form>
        </AuthCard>
      ) : null}

      {step.name === "recovery" ? (
        <AuthCard
          step={3}
          title="Save your recovery codes"
          description="If you lose your phone, each code signs you in once. They won't be shown again."
        >
          <div className="space-y-4">
            <ul className="grid grid-cols-2 gap-x-4 gap-y-1.5 border bg-muted/40 p-4 text-center font-mono text-sm tracking-wider">
              {step.codes.map((value) => (
                <li key={value}>{value}</li>
              ))}
            </ul>
            <div className="grid grid-cols-2 gap-2">
              <Button autoFocus variant="outline" onClick={() => clip(step.codes.join("\n"))}>
                <Copy className="size-4" /> Copy
              </Button>
              <Button variant="outline" onClick={() => download(step.codes)}>
                <Download className="size-4" /> Download
              </Button>
            </div>
            <label className="flex cursor-pointer items-center gap-2.5 text-sm">
              <Checkbox checked={saved} onCheckedChange={(value) => setSaved(!!value)} />
              I have saved these codes somewhere safe
            </label>
            <Button disabled={!saved} className={SUBMIT_CLASS} onClick={() => reloadTo(next)}>
              <Check className="size-4" /> Continue
            </Button>
          </div>
        </AuthCard>
      ) : null}
    </AuthFrame>
  );
}
