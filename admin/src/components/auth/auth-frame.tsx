import { Lock, ShieldCheck, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { BrandMark } from "@/components/shell/brand-mark";
import type { Branding } from "@/lib/branding-types";
import { cn } from "@/lib/utils";

import { AuthArt } from "./auth-art";

export type TrustBadge = { icon: LucideIcon; label: string };

const DEFAULT_BADGES: TrustBadge[] = [
  { icon: ShieldCheck, label: "2-step sign-in" },
  { icon: Lock, label: "Encrypted" },
];

/**
 * The scene behind every signed-out page: the organization's image, or the drawn
 * sunrise until one is uploaded, with its name above and the page's message below.
 * On a phone the scene shrinks to a banner and the card sits just under it.
 */
export function AuthFrame({
  branding,
  headline,
  message,
  badges = DEFAULT_BADGES,
  children,
}: {
  branding: Branding;
  headline: string;
  message: string;
  badges?: TrustBadge[];
  children: ReactNode;
}) {
  return (
    <div className="relative flex min-h-svh w-full flex-col overflow-hidden bg-background lg:block">
      <div className="relative h-40 shrink-0 overflow-hidden sm:h-52 lg:absolute lg:inset-0 lg:h-auto">
        {branding.login_image_url ? (
          <>
            {/* On a phone only the artwork side shows, as the rest is left empty for the card. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={branding.login_image_url}
              alt=""
              className="absolute inset-y-0 left-0 h-full w-[220%] max-w-none object-cover object-left lg:w-full"
            />
            <div aria-hidden className="absolute inset-0 hidden bg-black/45 dark:block" />
          </>
        ) : (
          <AuthArt />
        )}
      </div>

      <div className="absolute inset-x-0 top-0 z-10 flex flex-col justify-between p-4 sm:p-6 lg:inset-y-0 lg:right-auto lg:w-[46%] lg:p-10 xl:p-12">
        <div className="flex items-center gap-3">
          <BrandMark
            branding={branding}
            className={cn(
              "size-11 shadow-lg ring-1 ring-white/25 lg:size-14",
              branding.logo_url && "bg-white p-1",
            )}
          />
          <div className="min-w-0 leading-tight [text-shadow:0_1px_6px_rgb(0_0_0/0.45)]">
            <p className="truncate text-base font-bold tracking-wide text-white lg:text-lg">{branding.display_name}</p>
            <p className="text-[11px] font-medium tracking-widest text-white/75 uppercase">Staff portal</p>
          </div>
        </div>

        {/* An uploaded image carries its own scene, and text over it would land on a face. */}
        <div
          className={cn(
            "hidden space-y-4 [text-shadow:0_1px_8px_rgb(0_0_0/0.6)]",
            !branding.login_image_url && "lg:block",
          )}
        >
          <h1 className="text-4xl leading-tight font-extrabold whitespace-pre-line text-white">{headline}</h1>
          <p className="max-w-72 text-sm leading-relaxed text-white/85">{message}</p>
          <ul className="flex items-center gap-4 text-xs text-white/75">
            {badges.map(({ icon: Icon, label }) => (
              <li key={label} className="flex items-center gap-1.5">
                <Icon className="size-3.5" />
                {label}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <main className="relative z-10 flex flex-1 items-start justify-center px-4 pb-6 lg:min-h-svh lg:items-center lg:justify-end lg:px-0 lg:py-6 lg:pr-[max(3rem,calc(27vw-13.5rem))]">
        {children}
      </main>
    </div>
  );
}

/** The card itself. `step` restarts the entrance, so each step arrives rather than swaps. */
export function AuthCard({
  step,
  steps = 3,
  title,
  description,
  children,
}: {
  step?: number;
  steps?: number;
  title: string;
  description: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      key={title}
      className="-mt-8 w-full max-w-md border bg-card/95 text-card-foreground shadow-2xl backdrop-blur-sm motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-2 motion-safe:duration-300 lg:mt-0"
    >
      <div className="space-y-4 p-5 sm:p-6">
        {step ? <StepBars step={step} steps={steps} /> : null}
        <header>
          <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{description}</p>
        </header>
        {children}
      </div>
    </section>
  );
}

function StepBars({ step, steps }: { step: number; steps: number }) {
  return (
    <div
      role="progressbar"
      aria-label="Sign-in steps"
      aria-valuemin={1}
      aria-valuemax={steps}
      aria-valuenow={step}
      className="flex items-center gap-1.5"
    >
      {Array.from({ length: steps }).map((_, index) => (
        <span
          key={index}
          className={cn(
            "h-1 transition-all duration-300",
            index + 1 === step ? "w-7 bg-primary" : index + 1 < step ? "w-3.5 bg-primary/40" : "w-3.5 bg-muted",
          )}
        />
      ))}
    </div>
  );
}
