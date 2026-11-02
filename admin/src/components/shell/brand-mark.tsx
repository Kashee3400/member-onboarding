import type { Branding } from "@/lib/branding-types";
import { cn } from "@/lib/utils";

/** The organization's logo, or its first letter on its colour until one is uploaded. */
export function BrandMark({ branding, className }: { branding: Branding; className?: string }) {
  if (branding.logo_url) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={branding.logo_url} alt="" className={cn("shrink-0 object-contain", className)} />
    );
  }
  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 items-center justify-center bg-primary text-sm font-bold text-primary-foreground",
        className,
      )}
    >
      {(branding.display_name || "M").charAt(0).toUpperCase()}
    </span>
  );
}
