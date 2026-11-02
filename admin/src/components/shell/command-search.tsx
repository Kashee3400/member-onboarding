"use client";

import { useQuery } from "@tanstack/react-query";
import { FileText, Search, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
} from "@/components/ui/command";
import { Kbd } from "@/components/shell/shortcuts-help";
import { useSession } from "@/hooks/use-session";
import { api } from "@/lib/api/client";
import { flatten, iconFor } from "@/lib/nav";

type SearchHit = { kind: "application" | "member"; id: string; title: string; subtitle: string; path: string };

const GROUPS = [
  { kind: "application", title: "Forms", icon: FileText },
  { kind: "member", title: "Members", icon: UserRound },
] as const;

/** Ctrl K, anywhere: forms and members from the server, and this person's pages. */
export function CommandSearch() {
  const router = useRouter();
  const { navigation } = useSession();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const q = text.trim();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        setOpen((value) => !value);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const { data, isFetching } = useQuery({
    queryKey: ["search", q],
    queryFn: ({ signal }) => api<SearchHit[]>("search", { query: { q }, signal }),
    enabled: open && q.length >= 2,
  });
  const hits = useMemo(() => data ?? [], [data]);

  const pages = useMemo(() => {
    const needle = q.toLowerCase();
    return flatten(navigation).filter(
      ({ item, group }) =>
        !needle || item.label.toLowerCase().includes(needle) || group?.label.toLowerCase().includes(needle),
    );
  }, [navigation, q]);

  const go = (path: string | null) => {
    setOpen(false);
    setText("");
    if (path) router.push(path);
  };

  return (
    <>
      <Button
        variant="outline"
        className="h-8 w-9 justify-start gap-2 px-2 text-muted-foreground sm:w-56"
        aria-label="Search"
        onClick={() => setOpen(true)}
      >
        <Search className="size-4" />
        <span className="hidden sm:inline">Search…</span>
        <span className="ml-auto hidden gap-0.5 sm:inline-flex">
          <Kbd>Ctrl</Kbd>
          <Kbd>K</Kbd>
        </span>
      </Button>
      <CommandDialog
        open={open}
        onOpenChange={setOpen}
        title="Search"
        description="Find a form, a member or a page"
        className="sm:max-w-xl"
      >
        {/* The server already matched, and pages are matched above: cmdk must not filter again. */}
        <Command shouldFilter={false}>
          <CommandInput
            autoFocus
            placeholder="Form number, name, member code, MPP…"
            value={text}
            onValueChange={setText}
          />
          <CommandList className="max-h-[60vh]">
            <CommandEmpty>{isFetching ? "Searching…" : "Nothing found."}</CommandEmpty>
            {GROUPS.map((group) => {
              const rows = hits.filter((hit) => hit.kind === group.kind);
              if (!rows.length) return null;
              return (
                <CommandGroup key={group.kind} heading={group.title}>
                  {rows.map((hit) => (
                    <CommandItem key={hit.path} value={`${hit.kind} ${hit.id}`} onSelect={() => go(hit.path)}>
                      <group.icon />
                      <span className="min-w-0">
                        <span className="block truncate">{hit.title}</span>
                        {hit.subtitle ? (
                          <span className="block truncate text-xs text-muted-foreground">{hit.subtitle}</span>
                        ) : null}
                      </span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              );
            })}
            {pages.length ? (
              <CommandGroup heading="Pages">
                {pages.map(({ item, group }) => {
                  const Icon = iconFor(item.icon);
                  return (
                    <CommandItem key={item.key} value={`page ${item.key}`} onSelect={() => go(item.path)}>
                      <Icon />
                      <span>{item.label}</span>
                      {group ? <CommandShortcut>{group.label}</CommandShortcut> : null}
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            ) : null}
          </CommandList>
        </Command>
      </CommandDialog>
    </>
  );
}
