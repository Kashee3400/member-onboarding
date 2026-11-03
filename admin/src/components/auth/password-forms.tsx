"use client";

import { Building2, CheckCircle2, MailCheck, UserRound, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type FormEvent, type ReactNode, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { api, auth, reloadTo } from "@/lib/api";

import { AuthCard } from "./auth-frame";
import { EmailField, IconField, LINK_CLASS, PasswordField, ProblemNote, SUBMIT_CLASS, staffEmail } from "./fields";

const PASSWORD_HELP = "At least 12 characters.";

function BackLink({ href = "/login", children = "Back to sign in" }: { href?: string; children?: ReactNode }) {
  return (
    <p className="text-center">
      <Link href={href} className={LINK_CLASS}>
        {children}
      </Link>
    </p>
  );
}

function Finished({ icon: Icon, children }: { icon: LucideIcon; children: ReactNode }) {
  return (
    <div className="flex items-start gap-3 border border-primary/30 bg-primary/8 p-3 text-sm">
      <Icon className="mt-0.5 size-5 shrink-0 text-primary" />
      <p>{children}</p>
    </div>
  );
}

export function ChangePasswordForm() {
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [problem, setProblem] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!current || !password) {
      setProblem("Enter your current password and a new one.");
      return;
    }
    if (password !== repeat) {
      setProblem("The two new passwords do not match.");
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      await auth("password/change", { current_password: current, new_password: password });
      reloadTo("/");
    } catch (failure) {
      setProblem(failure);
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Set a new password" description="Use something you don't use anywhere else.">
      <form noValidate onSubmit={submit} className="space-y-4">
        <ProblemNote problem={problem} />
        <PasswordField
          id="current_password"
          label="Current password"
          autoFocus
          autoComplete="current-password"
          value={current}
          onChange={(event) => setCurrent(event.target.value)}
        />
        <PasswordField
          id="new_password"
          label="New password"
          help={PASSWORD_HELP}
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <PasswordField
          id="repeat"
          label="Repeat new password"
          autoComplete="new-password"
          value={repeat}
          onChange={(event) => setRepeat(event.target.value)}
        />
        <Button type="submit" disabled={busy} className={SUBMIT_CLASS}>
          {busy ? "Saving…" : "Save password"}
        </Button>
        <BackLink href="/">Back to the portal</BackLink>
      </form>
    </AuthCard>
  );
}

export function ForgotPasswordForm({ organization, domain = "" }: { organization: string; domain?: string }) {
  const [org, setOrg] = useState("");
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [problem, setProblem] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const slug = organization || org.trim();
    if (!slug || !email.trim()) {
      setProblem(`Enter your ${slug ? "email" : "organization"} to continue.`);
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      await auth("password/forgot", { email: staffEmail(email, domain), organization: slug });
      setSent(true);
    } catch (failure) {
      setProblem(failure);
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <AuthCard step={2} steps={2} title="Check your email" description="We have sent the next step to your inbox.">
        <div className="space-y-4">
          <Finished icon={MailCheck}>If that account exists, a reset link is on its way. It works for one hour.</Finished>
          <BackLink />
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      step={1}
      steps={2}
      title="Reset your password"
      description="Enter your email and we will send you a link to choose a new one."
    >
      <form noValidate onSubmit={submit} className="space-y-4">
        <ProblemNote problem={problem} />
        {organization ? null : (
          <IconField
            id="organization"
            label="Organization"
            icon={Building2}
            autoFocus
            autoComplete="organization"
            value={org}
            onChange={(event) => setOrg(event.target.value)}
          />
        )}
        <EmailField
          autoFocus={!!organization}
          domain={domain}
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <Button type="submit" disabled={busy} className={SUBMIT_CLASS}>
          {busy ? "Sending…" : "Send reset link"}
        </Button>
        <BackLink />
      </form>
    </AuthCard>
  );
}

type Invitation = { email: string; full_name: string; organization: string };

/** From the invitation email: the person chooses their password and confirms their name. */
export function AcceptInviteForm() {
  const query = useSearchParams();
  const organization = query.get("organization") ?? "";
  const token = query.get("token") ?? "";
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  const [invalid, setInvalid] = useState<unknown>(null);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [done, setDone] = useState(false);
  const [problem, setProblem] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!organization || !token) return;
    const params = new URLSearchParams({ organization, token });
    api
      .get<Invitation>(`public/invitations?${params}`)
      .then((found) => {
        setInvitation(found);
        setName(found.full_name);
      })
      .catch(setInvalid);
  }, [organization, token]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || !password) {
      setProblem("Enter your name and a password.");
      return;
    }
    if (password !== repeat) {
      setProblem("The two passwords do not match.");
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      await api.post("public/invitations", { organization, token, full_name: name.trim(), password });
      setDone(true);
    } catch (failure) {
      setProblem(failure);
    } finally {
      setBusy(false);
    }
  }

  if (!organization || !token || invalid) {
    return (
      <AuthCard
        title="This invitation cannot be used"
        description="It may have expired, been used already, or been replaced by a newer one. Ask your administrator to send it again."
      >
        <BackLink />
      </AuthCard>
    );
  }

  if (!invitation) {
    return (
      <AuthCard title="Opening your invitation" description="One moment…">
        <div className="h-24" />
      </AuthCard>
    );
  }

  if (done) {
    return (
      <AuthCard step={2} steps={2} title="Your account is ready" description="Sign in with your email and the new password.">
        <div className="space-y-4">
          <Finished icon={CheckCircle2}>
            If your role signs forms, the portal will ask for your signature after you sign in.
          </Finished>
          <Link
            href="/login"
            className={`${SUBMIT_CLASS} inline-flex items-center justify-center text-sm text-primary-foreground outline-none focus-visible:ring-3 focus-visible:ring-ring/50`}
          >
            Sign in
          </Link>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      step={1}
      steps={2}
      title={`Join ${invitation.organization}`}
      description={`You were invited as ${invitation.email}. Check your name as it should appear on official forms, then choose a password.`}
    >
      <form noValidate onSubmit={submit} className="space-y-4">
        <ProblemNote problem={problem} />
        <IconField
          id="full_name"
          label="Official name"
          icon={UserRound}
          help="As on your ID. It is printed next to your signature."
          autoComplete="name"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <PasswordField
          id="new_password"
          label="Password"
          help={PASSWORD_HELP}
          autoFocus
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <PasswordField
          id="repeat"
          label="Repeat password"
          autoComplete="new-password"
          value={repeat}
          onChange={(event) => setRepeat(event.target.value)}
        />
        <Button type="submit" disabled={busy} className={SUBMIT_CLASS}>
          {busy ? "Setting up…" : "Create my account"}
        </Button>
      </form>
    </AuthCard>
  );
}

export function ResetPasswordForm() {
  const query = useSearchParams();
  const uid = query.get("uid");
  const token = query.get("token");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [done, setDone] = useState(false);
  const [problem, setProblem] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!password) {
      setProblem("Enter a new password.");
      return;
    }
    if (password !== repeat) {
      setProblem("The two passwords do not match.");
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      await auth("password/reset", { uid, token, new_password: password });
      setDone(true);
    } catch (failure) {
      setProblem(failure);
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <AuthCard step={2} steps={2} title="Password changed" description="You can sign in with it now.">
        <div className="space-y-4">
          <Finished icon={CheckCircle2}>Your new password is ready.</Finished>
          <Link
            href="/login"
            className={`${SUBMIT_CLASS} inline-flex items-center justify-center text-sm text-primary-foreground outline-none focus-visible:ring-3 focus-visible:ring-ring/50`}
          >
            Sign in
          </Link>
        </div>
      </AuthCard>
    );
  }

  if (!uid || !token) {
    return (
      <AuthCard title="This link is not complete" description="Open the link from your email again, or ask for a new one.">
        <BackLink href="/forgot-password">Ask for a new link</BackLink>
      </AuthCard>
    );
  }

  return (
    <AuthCard step={1} steps={2} title="Choose a new password" description="Use something you don't use anywhere else.">
      <form noValidate onSubmit={submit} className="space-y-4">
        <ProblemNote problem={problem} />
        <PasswordField
          id="new_password"
          label="New password"
          help={PASSWORD_HELP}
          autoFocus
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <PasswordField
          id="repeat"
          label="Repeat new password"
          autoComplete="new-password"
          value={repeat}
          onChange={(event) => setRepeat(event.target.value)}
        />
        <Button type="submit" disabled={busy} className={SUBMIT_CLASS}>
          {busy ? "Saving…" : "Save password"}
        </Button>
        <BackLink />
      </form>
    </AuthCard>
  );
}
