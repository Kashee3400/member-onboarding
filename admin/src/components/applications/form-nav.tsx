"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Kbd } from "@/components/shell/shortcuts-help";
import { Button } from "@/components/ui/button";
import { api, type Page } from "@/lib/api/client";
import { isTyping } from "@/lib/shortcuts";
import type { ApplicationSummary } from "@/lib/types";

/**
 * Moves through the queue this form sits in, oldest first, as the queue page does:
 * J for the next form, K for the one before. 1 to 8 jump to that review step.
 */
export function FormNav({
  id,
  status,
  steps,
}: {
  id: string;
  status: string;
  /** The steps shown on the page, by their number on the form. */
  steps: { number: number; key: string }[];
}) {
  const router = useRouter();
  const inQueue = status.startsWith("pending");
  const queue = useQuery({
    queryKey: ["queue", "around", status],
    queryFn: () =>
      api<Page<ApplicationSummary>>("applications", {
        query: { status, ordering: "waiting_since", page_size: 200 },
      }),
    enabled: inQueue,
    staleTime: 30_000,
  });
  const ids = queue.data?.results.map((row) => row.id) ?? [];
  const at = ids.indexOf(id);
  const previous = at > 0 ? ids[at - 1] : null;
  const next = at >= 0 && at < ids.length - 1 ? ids[at + 1] : null;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event) || event.metaKey || event.ctrlKey || event.altKey) return;
      if (document.querySelector("[role=dialog]")) return;
      const key = event.key.toLowerCase();
      if (key === "j" && next) router.push(`/applications/${next}`);
      else if (key === "k" && previous) router.push(`/applications/${previous}`);
      else if (/^[1-9]$/.test(key)) {
        const step = steps.find((item) => item.number === Number(key));
        const target = step ? document.getElementById(`section-step-${step.key}`) : null;
        if (!target) return;
        event.preventDefault();
        target.scrollIntoView({ behavior: "smooth" });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [next, previous, router, steps]);

  if (!inQueue || at < 0) return null;
  return (
    <div className="flex items-center gap-1">
      <span className="mr-1 text-xs text-muted-foreground tabular-nums">
        {at + 1} of {ids.length}
      </span>
      <Button
        variant="outline"
        size="sm"
        disabled={!previous}
        onClick={() => previous && router.push(`/applications/${previous}`)}
        aria-label="Previous form (K)"
      >
        <ChevronLeft /> <Kbd className="hidden sm:inline-flex">K</Kbd>
      </Button>
      <Button
        variant="outline"
        size="sm"
        disabled={!next}
        onClick={() => next && router.push(`/applications/${next}`)}
        aria-label="Next form (J)"
      >
        <Kbd className="hidden sm:inline-flex">J</Kbd> <ChevronRight />
      </Button>
    </div>
  );
}
