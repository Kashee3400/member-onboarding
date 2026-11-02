"use client";

import { AlertTriangle, Eye, EyeOff, Info, Lock, Mail, type LucideIcon } from "lucide-react";
import { useEffect, useState, type ComponentProps, type ReactNode } from "react";

import { Field } from "@/components/common/field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { InputGroup, InputGroupAddon, InputGroupInput, InputGroupText } from "@/components/ui/input-group";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

/** The strong button on each step: the brand colour, deepening towards its end. */
export const SUBMIT_CLASS =
  "h-10 w-full bg-linear-to-r from-primary to-[color-mix(in_oklch,var(--primary)_78%,black)] font-semibold shadow-sm transition-[filter] hover:brightness-105";

export const LINK_CLASS =
  "text-sm text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:text-foreground focus-visible:underline";

/** What to tell a person about a failed request. */
export function problemText(problem: unknown): string {
  if (problem instanceof ApiError) {
    if (problem.status === 429) return "Too many tries. Wait a few minutes and try again.";
    // These forms are short enough that the sentence alone says which box it means.
    return problem.summary.replace(/^\w+: /, "");
  }
  if (typeof problem === "string") return problem;
  return "We could not reach the server. Check your connection and try again.";
}

export function ProblemNote({ problem }: { problem: unknown }) {
  if (!problem) return null;
  return (
    <Alert variant="destructive" className="border-destructive/35 bg-destructive/6">
      <AlertTriangle />
      <AlertDescription>{problemText(problem)}</AlertDescription>
    </Alert>
  );
}

export function InfoNote({ children }: { children: ReactNode }) {
  return (
    <div
      role="status"
      className="flex items-start gap-2 border border-primary/30 bg-primary/8 px-3 py-2 text-sm text-foreground"
    >
      <Info className="mt-0.5 size-4 shrink-0 text-primary" />
      <span>{children}</span>
    </div>
  );
}

export function IconField({
  id,
  label,
  icon: Icon,
  help,
  ...input
}: { id: string; label: string; icon: LucideIcon; help?: ReactNode } & ComponentProps<typeof InputGroupInput>) {
  return (
    <Field label={label} htmlFor={id} help={help}>
      <InputGroup className="h-10">
        <InputGroupAddon align="inline-start">
          <InputGroupText>
            <Icon className="size-4 text-muted-foreground" />
          </InputGroupText>
        </InputGroupAddon>
        <InputGroupInput id={id} {...input} />
      </InputGroup>
    </Field>
  );
}

export function EmailField(props: Omit<ComponentProps<typeof IconField>, "id" | "label" | "icon">) {
  return (
    <IconField
      id="email"
      label="Email"
      icon={Mail}
      type="email"
      autoComplete="username"
      placeholder="you@company.com"
      {...props}
    />
  );
}

export function PasswordField({
  id,
  label,
  help,
  ...input
}: { id: string; label: string; help?: ReactNode } & ComponentProps<typeof InputGroupInput>) {
  const [shown, setShown] = useState(false);
  const [focused, setFocused] = useState(false);
  const capsLock = useCapsLock();

  return (
    <Field label={label} htmlFor={id} help={help}>
      <InputGroup className="h-10">
        <InputGroupAddon align="inline-start">
          <InputGroupText>
            <Lock className="size-4 text-muted-foreground" />
          </InputGroupText>
        </InputGroupAddon>
        <InputGroupInput
          id={id}
          type={shown ? "text" : "password"}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          {...input}
        />
        <InputGroupAddon align="inline-end">
          <button
            type="button"
            onClick={() => setShown((value) => !value)}
            aria-label={shown ? "Hide password" : "Show password"}
            aria-pressed={shown}
            className="flex size-7 items-center justify-center text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
          >
            {shown ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </button>
        </InputGroupAddon>
      </InputGroup>
      {capsLock && focused ? (
        <p className="flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-300">
          <AlertTriangle className="size-3.5 shrink-0" />
          Caps Lock is on.
        </p>
      ) : null}
    </Field>
  );
}

function useCapsLock() {
  const [on, setOn] = useState(false);
  useEffect(() => {
    const read = (event: KeyboardEvent) => {
      if (event.getModifierState) setOn(event.getModifierState("CapsLock"));
    };
    window.addEventListener("keydown", read);
    window.addEventListener("keyup", read);
    return () => {
      window.removeEventListener("keydown", read);
      window.removeEventListener("keyup", read);
    };
  }, []);
  return on;
}

export function CodeBoxes({
  value,
  onChange,
  onComplete,
  label,
  invalid = false,
}: {
  value: string;
  onChange: (value: string) => void;
  onComplete: (value: string) => void;
  label: string;
  invalid?: boolean;
}) {
  return (
    <div className="flex justify-center">
      <InputOTP
        autoFocus
        maxLength={6}
        pattern="^[0-9]*$"
        inputMode="numeric"
        autoComplete="one-time-code"
        aria-label={label}
        value={value}
        onChange={onChange}
        onComplete={onComplete}
      >
        <InputOTPGroup className="gap-1.5 has-aria-invalid:ring-0 sm:gap-2">
          {Array.from({ length: 6 }).map((_, index) => (
            <InputOTPSlot
              key={index}
              index={index}
              aria-invalid={invalid || undefined}
              className={cn(
                "size-10 border bg-background text-lg font-semibold tabular-nums sm:size-11",
                "transition-[transform,box-shadow] duration-100 data-[active=true]:z-10 data-[active=true]:-translate-y-px data-[active=true]:border-primary data-[active=true]:shadow-(--lift) data-[active=true]:ring-0",
              )}
            />
          ))}
        </InputOTPGroup>
      </InputOTP>
    </div>
  );
}
