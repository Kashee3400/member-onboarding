"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Bookmark,
  BookmarkPlus,
  Check,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Columns3,
  Download,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { toast } from "sonner";

import { Listbox } from "@/components/common/listbox";
import { AsyncSelect } from "@/components/common/async-select";
import { IconInput } from "@/components/common/form-input";
import { SearchBox } from "@/components/common/search-box";
import { EmptyState, ErrorState } from "@/components/common/states";
import { StatusTabs } from "@/components/common/status-tabs";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, api, cursorOf, type Page } from "@/lib/api/client";
import { useListKeys } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";

/**
 * The admin panel's table, for every list.
 *
 * Data comes from an API endpoint in either shape:
 * - pages (`{count, results, next, previous}`): search (`?q=`), sorting
 *   (`?ordering=`) and paging happen on the server;
 * - a plain array (small lists: tax classes, disputes…): search, sorting and
 *   paging happen here, over what came back.
 *
 * Search, filters, tabs, sorting and the page live in the URL, so a view can be
 * bookmarked or sent — or saved under a name ("Views", remembered in this
 * browser), next to the page's ready-made `views`. Columns can be hidden, rows
 * selected across pages for bulk actions, and rows exported as CSV: this page,
 * the selection, or everything that matches.
 */

export type Column<T> = {
  id: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  /** Makes the column sortable: the `?ordering=` key on the server, or the key for client sorting. */
  sortKey?: string;
  /** What client-side sorting compares (default: `csv`). */
  sortValue?: (row: T) => string | number | null | undefined;
  /** The text for CSV export and client-side search. */
  csv?: (row: T) => string | number | null | undefined;
  align?: "left" | "right" | "center";
  hideBelow?: "sm" | "md" | "lg" | "xl";
  defaultHidden?: boolean;
  required?: boolean;
  className?: string;
};

export type Filters = Record<string, string | undefined>;
type SetFilter = (key: string, value: string | undefined) => void;
/** Several filters in one change (two setFilter calls in a row would undo each other). */
type SetFilters = (values: Record<string, string | undefined>) => void;

type Props<T> = {
  /** Stable name: keys the remembered columns and the cache. */
  id: string;
  endpoint: string;
  columns: Column<T>[];
  rowKey: (row: T) => string;
  /** Query params always sent (not in the URL). */
  baseParams?: Record<string, string | undefined>;
  /** Prefix for this table's URL params, when a page shows more than one table. */
  urlPrefix?: string;
  /** Status-style tabs over the table; each sets the `filter` param. */
  tabs?: { filter: string; options: { value: string; label: string; count?: number }[] };
  /** Filter controls; they read and write `filters` (kept in the URL). */
  filters?: (state: { filters: Filters; setFilter: SetFilter; setFilters: SetFilters }) => ReactNode;
  defaultFilters?: Filters;
  /** For array endpoints: which rows a filter keeps (filters the server ignores). */
  clientFilter?: (row: T, filters: Record<string, string | undefined>) => boolean;
  /** Hide the search box (an endpoint that can't search, on a client list without text). */
  searchable?: boolean;
  searchPlaceholder?: string;
  defaultOrdering?: string;
  pageSizes?: number[];
  onRowClick?: (row: T) => void;
  /** A and D on the row J / K reached. Enter is always `onRowClick`. */
  rowKeys?: { onApprove?: (row: T) => void; onDismiss?: (row: T) => void };
  /** Bulk actions for the selected rows; when given, rows get checkboxes. */
  bulkActions?: (selected: T[], clear: () => void) => ReactNode;
  /** Rows that can't be selected. */
  canSelect?: (row: T) => boolean;
  empty?: ReactNode;
  toolbar?: ReactNode;
  /** Shown under the toolbar, above the table (a hint for this tab…). */
  above?: (filters: Filters, data: unknown) => ReactNode;
  exportName?: string;
  /** Ready-made views for this list ("Today's refunds"), offered under "Views". */
  views?: TableView[];
};

/** A named set of search, filters and sorting for one table. */
export type TableView = { name: string; filters?: Filters; q?: string; ordering?: string };

/** Most rows "Everything that matches" fetches for a CSV. */
const EXPORT_LIMIT = 5000;

const HIDE: Record<NonNullable<Column<unknown>["hideBelow"]>, string> = {
  sm: "hidden sm:table-cell",
  md: "hidden md:table-cell",
  lg: "hidden lg:table-cell",
  xl: "hidden xl:table-cell",
};

const ALL = "__all";

// Which columns are hidden, per table, remembered in this browser.
const COLUMNS_EVENT = "mo-table-columns";
function readColumns(id: string): string | null {
  try {
    return localStorage.getItem(`mo-table:${id}:hidden`);
  } catch {
    return null; // private window / blocked storage: the defaults apply
  }
}
function writeColumns(id: string, value: string) {
  try {
    localStorage.setItem(`mo-table:${id}:hidden`, value);
  } catch {
    // not remembered
  }
  window.dispatchEvent(new Event(COLUMNS_EVENT));
}
function subscribeColumns(onChange: () => void) {
  window.addEventListener(COLUMNS_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(COLUMNS_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

// Views a person saved for a table, in this browser.
type SavedView = { name: string; query: string };
const VIEWS_EVENT = "mo-table-views";
function readViews(id: string): string {
  try {
    return localStorage.getItem(`mo-table:${id}:views`) ?? "[]";
  } catch {
    return "[]";
  }
}
function writeViews(id: string, views: SavedView[]) {
  try {
    localStorage.setItem(`mo-table:${id}:views`, JSON.stringify(views));
  } catch {
    toast.error("This browser won't keep saved views.");
  }
  window.dispatchEvent(new Event(VIEWS_EVENT));
}
function subscribeViews(onChange: () => void) {
  window.addEventListener(VIEWS_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(VIEWS_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

const compare = (a: unknown, b: unknown) => {
  if (a === b) return 0;
  if (a === null || a === undefined || a === "") return 1;
  if (b === null || b === undefined || b === "") return -1;
  const na = Number(a);
  const nb = Number(b);
  if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb;
  return String(a).localeCompare(String(b), "en", { numeric: true, sensitivity: "base" });
};

export function DataTable<T>({
  id,
  endpoint,
  columns,
  rowKey,
  baseParams,
  urlPrefix = "",
  tabs,
  filters: renderFilters,
  defaultFilters: givenDefaults,
  searchable = true,
  searchPlaceholder = "Search",
  defaultOrdering,
  pageSizes = [20, 50, 100],
  onRowClick,
  rowKeys,
  bulkActions,
  canSelect,
  empty,
  toolbar,
  above,
  exportName,
  clientFilter,
  views: presets,
}: Props<T>) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const k = (name: string) => `${urlPrefix}${name}`;
  const defaultFilters = useMemo(
    () => ({ ...(tabs ? { [tabs.filter]: tabs.options[0]?.value } : {}), ...givenDefaults }),
    [tabs, givenDefaults],
  );

  // --- state that lives in the URL -------------------------------------------------
  const q = params.get(k("q")) ?? "";
  const ordering = params.get(k("ordering")) ?? defaultOrdering ?? "";
  const cursor = params.get(k("cursor"));
  const pageIndex = Number(params.get(k("page"))) || 0;
  const pageSize = Number(params.get(k("page_size"))) || pageSizes[0];
  const filterKeys = useMemo(() => {
    const keys = new Set(Object.keys(defaultFilters));
    params.forEach((_, name) => {
      if (name.startsWith(k("f_"))) keys.add(name.slice(k("f_").length));
    });
    return [...keys];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, defaultFilters, urlPrefix]);
  const filters: Filters = useMemo(
    () => Object.fromEntries(filterKeys.map((f) => [f, params.get(k(`f_${f}`)) ?? defaultFilters[f]])),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [filterKeys, params, defaultFilters, urlPrefix],
  );

  const update = (changes: Record<string, string | undefined | null>, keepPage = false) => {
    const next = new URLSearchParams(params.toString());
    for (const [name, v] of Object.entries(changes)) {
      if (v === undefined || v === null || v === "") next.delete(k(name));
      else next.set(k(name), v);
    }
    if (!keepPage) {
      next.delete(k("cursor"));
      next.delete(k("page"));
    }
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };
  const setFilter: SetFilter = (key, value) =>
    update({ [`f_${key}`]: value === defaultFilters[key] ? undefined : value || ALL });
  const setFilters: SetFilters = (values) =>
    update(
      Object.fromEntries(
        Object.entries(values).map(([key, value]) => [
          `f_${key}`,
          value === defaultFilters[key] ? undefined : value || ALL,
        ]),
      ),
    );

  // A filter set to "everything" is stored as __all so it beats a default.
  const sentFilters = Object.fromEntries(
    Object.entries(filters).map(([f, v]) => [f, v === ALL ? undefined : v]),
  ) as Record<string, string | undefined>;

  // --- data ---------------------------------------------------------------------------
  // Keys start with "queue": every write that refreshes the queues refreshes tables too.
  const query = useQuery({
    queryKey: ["queue", "table", id, endpoint, baseParams, sentFilters, q, ordering, cursor, pageIndex, pageSize],
    queryFn: ({ signal }) =>
      api<Page<T> | T[]>(endpoint, {
        query: {
          ...baseParams,
          ...sentFilters,
          q: q || undefined,
          ordering: ordering || undefined,
          cursor,
          // Numbered pages (count, jump to a page) where the API offers them;
          // a cursor from an older-style endpoint still works.
          page: cursor ? undefined : pageIndex + 1,
          page_size: pageSize,
        },
        signal,
      }),
    placeholderData: keepPreviousData,
  });
  const clientSide = Array.isArray(query.data);

  const filterSig = JSON.stringify(sentFilters);
  const { rows, all, total, hasPrev, hasNext } = useMemo(() => {
    const data = query.data;
    if (!data) return { rows: [] as T[], all: [] as T[], total: 0, hasPrev: false, hasNext: false };
    if (!Array.isArray(data)) {
      return {
        rows: data.results,
        all: null,
        total: typeof data.count === "number" ? data.count : -1,
        hasPrev: !!data.previous,
        hasNext: !!data.next,
      };
    }
    let list = clientFilter ? data.filter((r) => clientFilter(r, sentFilters)) : data;
    const needle = q.trim().toLowerCase();
    if (needle) {
      list = list.filter((r) =>
        columns.some((c) =>
          String((c.csv ?? c.sortValue)?.(r) ?? "")
            .toLowerCase()
            .includes(needle),
        ),
      );
    }
    const key = ordering.replace(/^-/, "");
    const col = key ? columns.find((c) => c.sortKey === key) : undefined;
    if (col) {
      const value = col.sortValue ?? col.csv ?? (() => "");
      const dir = ordering.startsWith("-") ? -1 : 1;
      list = [...list].sort((a, b) => dir * compare(value(a), value(b)));
    }
    const start = pageIndex * pageSize;
    return {
      rows: list.slice(start, start + pageSize),
      all: list,
      total: list.length,
      hasPrev: pageIndex > 0,
      hasNext: start + pageSize < list.length,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query.data, q, ordering, columns, pageIndex, pageSize, clientFilter, filterSig]);

  // A page that emptied (rows were acted on, or a filter narrowed it) is past the end.
  const pastTheEnd = query.error instanceof ApiError && query.error.status === 404 && pageIndex > 0;
  useEffect(() => {
    if (pastTheEnd) update({ page: undefined }, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pastTheEnd]);

  const keys = useListKeys(rows.length, {
    onOpen: onRowClick ? (index) => onRowClick(rows[index]) : undefined,
    onApprove: rowKeys?.onApprove ? (index) => rowKeys.onApprove!(rows[index]) : undefined,
    onDismiss: rowKeys?.onDismiss ? (index) => rowKeys.onDismiss!(rows[index]) : undefined,
  });

  // --- columns ------------------------------------------------------------------------
  const defaults = useMemo(() => JSON.stringify(columns.filter((c) => c.defaultHidden).map((c) => c.id)), [columns]);
  const stored = useSyncExternalStore(
    subscribeColumns,
    () => readColumns(id) ?? defaults,
    () => defaults,
  );
  const hidden = useMemo(() => new Set(JSON.parse(stored) as string[]), [stored]);
  const toggleColumn = (colId: string) => {
    const next = new Set(hidden);
    if (next.has(colId)) next.delete(colId);
    else next.add(colId);
    writeColumns(id, JSON.stringify([...next]));
  };
  const shown = columns.filter((c) => c.required || !hidden.has(c.id));

  // --- selection (survives paging) -----------------------------------------------------
  const [selected, setSelected] = useState<Map<string, T>>(() => new Map());
  const clear = () => setSelected(new Map());
  const pickable = rows.filter((r) => !canSelect || canSelect(r));
  const allOnPage = pickable.length > 0 && pickable.every((r) => selected.has(rowKey(r)));
  const someOnPage = pickable.some((r) => selected.has(rowKey(r)));
  const togglePage = () =>
    setSelected((m) => {
      const next = new Map(m);
      for (const r of pickable) {
        if (allOnPage) next.delete(rowKey(r));
        else next.set(rowKey(r), r);
      }
      return next;
    });
  const toggleRow = (r: T) =>
    setSelected((m) => {
      const next = new Map(m);
      const key = rowKey(r);
      if (next.has(key)) next.delete(key);
      else next.set(key, r);
      return next;
    });

  const sortBy = (key: string) => {
    const next = ordering === key ? `-${key}` : ordering === `-${key}` ? (defaultOrdering ?? "") : key;
    update({ ordering: next === (defaultOrdering ?? "") ? undefined : next });
  };

  const writeCsv = (source: T[], suffix = "") => {
    const cols = shown.filter((c) => c.csv);
    const esc = (v: unknown) => {
      const s = v === null || v === undefined ? "" : String(v);
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const lines = [
      cols.map((c) => esc(typeof c.header === "string" ? c.header : c.id)).join(","),
      ...source.map((r) => cols.map((c) => esc(c.csv!(r))).join(",")),
    ];
    const blob = new Blob([`﻿${lines.join("\n")}`], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${exportName ?? id}${suffix}-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  const [exporting, setExporting] = useState(false);
  /** Every row that matches the search and filters — page by page from the server. */
  const exportAll = async () => {
    if (all) {
      writeCsv(all, "-all");
      return;
    }
    setExporting(true);
    const toastId = toast.loading("Collecting rows…");
    try {
      const out: T[] = [];
      let page = 1;
      let more = true;
      while (more && out.length < EXPORT_LIMIT) {
        const found: Page<T> = await api<Page<T>>(endpoint, {
          query: {
            ...baseParams,
            ...sentFilters,
            q: q || undefined,
            ordering: ordering || undefined,
            page,
            page_size: 1000,
          },
        });
        out.push(...found.results);
        more = !!found.next;
        page += 1;
        toast.loading(`Collecting rows… ${out.length}`, { id: toastId });
      }
      writeCsv(out.slice(0, EXPORT_LIMIT), "-all");
      toast.success(
        out.length >= EXPORT_LIMIT
          ? `First ${EXPORT_LIMIT} rows exported — narrow the filters for the rest`
          : `${out.length} rows exported`,
        { id: toastId },
      );
    } catch {
      toast.error("Couldn't collect the rows. Try again.", { id: toastId });
    } finally {
      setExporting(false);
    }
  };

  // --- views: a named search + filters + sorting -----------------------------------------
  const ownKey = (name: string) =>
    name === k("q") || name === k("ordering") || name === k("page_size") || name.startsWith(k("f_"));
  const own = new URLSearchParams();
  params.forEach((v, name) => {
    if (ownKey(name)) own.set(name, v);
  });
  own.sort();
  const currentQuery = own.toString();
  const presetQuery = (v: TableView) => {
    const p = new URLSearchParams();
    for (const [f, val] of Object.entries(v.filters ?? {})) {
      if (val !== undefined && val !== defaultFilters[f]) p.set(k(`f_${f}`), val || ALL);
    }
    if (v.q) p.set(k("q"), v.q);
    if (v.ordering && v.ordering !== defaultOrdering) p.set(k("ordering"), v.ordering);
    p.sort();
    return p.toString();
  };
  const savedRaw = useSyncExternalStore(
    subscribeViews,
    () => readViews(id),
    () => "[]",
  );
  const saved = useMemo(() => JSON.parse(savedRaw) as SavedView[], [savedRaw]);
  const applyQuery = (query: string) => {
    const next = new URLSearchParams(params.toString());
    [...next.keys()].filter(ownKey).forEach((name) => next.delete(name));
    next.delete(k("cursor"));
    next.delete(k("page"));
    new URLSearchParams(query).forEach((v, name) => next.set(name, v));
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };
  const [naming, setNaming] = useState(false);
  const [viewName, setViewName] = useState("");
  const saveView = () => {
    const name = viewName.trim();
    if (!name) return;
    writeViews(id, [...saved.filter((v) => v.name !== name), { name, query: currentQuery }]);
    setNaming(false);
    setViewName("");
    toast.success(`Saved “${name}”`);
  };
  const activeView =
    (presets ?? []).find((v) => presetQuery(v) === currentQuery)?.name ??
    saved.find((v) => v.query === currentQuery)?.name;

  const activeFilters = Object.entries(filters).filter(
    ([f, v]) => v && v !== ALL && v !== defaultFilters[f] && f !== tabs?.filter,
  );
  const alignClass = (c: Column<T>) => (c.align === "right" ? "text-right" : c.align === "center" ? "text-center" : "");
  const selectable = !!bulkActions;
  const numbered = clientSide || total >= 0;
  const pages = numbered ? Math.max(1, Math.ceil(total / pageSize)) : 0;
  /** Go to a page by number (1-based) — tables whose API counts. */
  const goTo = (n: number) => {
    const target = Math.min(Math.max(1, Math.round(n) || 1), Math.max(pages, 1));
    update({ page: target > 1 ? String(target - 1) : undefined, cursor: undefined }, true);
  };
  const goPage = (dir: 1 | -1) => {
    const data = query.data;
    if (numbered) goTo(pageIndex + 1 + dir);
    else if (data && !Array.isArray(data)) {
      update({ cursor: cursorOf(dir > 0 ? data.next : data.previous) }, true);
    }
  };

  return (
    <div className="space-y-3">
      {tabs ? (
        <StatusTabs
          value={
            filters[tabs.filter] === ALL
              ? (tabs.options.find((o) => o.value === "")?.value ?? ALL)
              : (filters[tabs.filter] ?? tabs.options[0]?.value ?? "")
          }
          onChange={(v) => setFilter(tabs.filter, v)}
          options={tabs.options}
        />
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        {searchable ? <SearchBox value={q} onChange={(v) => update({ q: v })} placeholder={searchPlaceholder} /> : null}
        {renderFilters?.({ filters, setFilter, setFilters })}
        {activeFilters.length || q ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              update(
                Object.fromEntries([
                  ["q", undefined],
                  ...filterKeys.filter((f) => f !== tabs?.filter).map((f) => [`f_${f}`, undefined]),
                ]),
              )
            }
          >
            <X /> Clear filters
          </Button>
        ) : null}
        <div className="ml-auto flex items-center gap-1">
          {toolbar}
          <Button variant="ghost" size="icon-sm" aria-label="Refresh" onClick={() => query.refetch()}>
            <RefreshCw className={cn(query.isFetching && "animate-spin")} />
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="ghost" size="sm" />}>
              <Bookmark />{" "}
              <span className={cn("max-w-32 truncate", !activeView && "hidden sm:inline")}>
                {activeView ?? "Views"}
              </span>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              {presets?.length ? (
                <DropdownMenuGroup>
                  <DropdownMenuLabel>Ready-made</DropdownMenuLabel>
                  {presets.map((v) => (
                    <DropdownMenuItem key={`p-${v.name}`} onClick={() => applyQuery(presetQuery(v))}>
                      {v.name}
                      {activeView === v.name ? <Check className="ml-auto" /> : null}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuGroup>
              ) : null}
              <DropdownMenuGroup>
                <DropdownMenuLabel>Saved by you</DropdownMenuLabel>
                {saved.length === 0 ? (
                  <p className="px-2 py-1 text-xs text-muted-foreground">
                    Set a search and filters, then save them here.
                  </p>
                ) : null}
                {saved.map((v) => (
                  <DropdownMenuItem key={`s-${v.name}`} onClick={() => applyQuery(v.query)}>
                    <span className="truncate">{v.name}</span>
                    <span className="ml-auto flex items-center gap-1">
                      {activeView === v.name ? <Check /> : null}
                      <button
                        type="button"
                        aria-label={`Delete ${v.name}`}
                        className="p-0.5 text-muted-foreground hover:text-destructive"
                        onClick={(e) => {
                          e.stopPropagation();
                          writeViews(
                            id,
                            saved.filter((x) => x.name !== v.name),
                          );
                        }}
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    </span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuGroup>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setNaming(true)} disabled={!currentQuery}>
                <BookmarkPlus /> Save this view…
              </DropdownMenuItem>
              {currentQuery ? (
                <DropdownMenuItem onClick={() => applyQuery("")}>
                  <X /> Back to the default
                </DropdownMenuItem>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
          {columns.some((c) => c.csv) ? (
            <DropdownMenu>
              <DropdownMenuTrigger render={<Button variant="ghost" size="sm" disabled={!rows.length || exporting} />}>
                <Download /> <span className="hidden sm:inline">Export</span>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-64">
                <DropdownMenuGroup>
                  <DropdownMenuLabel>Download as CSV</DropdownMenuLabel>
                  <DropdownMenuItem onClick={() => writeCsv(rows)}>This page · {rows.length} rows</DropdownMenuItem>
                  {selected.size ? (
                    <DropdownMenuItem onClick={() => writeCsv([...selected.values()], "-selected")}>
                      Selected · {selected.size} rows
                    </DropdownMenuItem>
                  ) : null}
                  <DropdownMenuItem onClick={exportAll}>
                    Everything that matches{all ? ` · ${all.length} rows` : ` (up to ${EXPORT_LIMIT})`}
                  </DropdownMenuItem>
                </DropdownMenuGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
          {columns.some((c) => !c.required) ? (
            <DropdownMenu>
              <DropdownMenuTrigger render={<Button variant="ghost" size="sm" />}>
                <Columns3 /> <span className="hidden sm:inline">Columns</span>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-52">
                <DropdownMenuGroup>
                  <DropdownMenuLabel>Show columns</DropdownMenuLabel>
                  {columns
                    .filter((c) => !c.required)
                    .map((c) => (
                      <DropdownMenuCheckboxItem
                        key={c.id}
                        checked={!hidden.has(c.id)}
                        onCheckedChange={() => toggleColumn(c.id)}
                        closeOnClick={false}
                      >
                        {typeof c.header === "string" ? c.header : c.id}
                      </DropdownMenuCheckboxItem>
                    ))}
                </DropdownMenuGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      </div>

      <Dialog open={naming} onOpenChange={setNaming}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Save this view</DialogTitle>
            <DialogDescription>
              The search, filters and sorting you have now, under a name. Kept in this browser.
            </DialogDescription>
          </DialogHeader>
          <IconInput
            leading={Bookmark}
            autoFocus
            placeholder="e.g. Big refunds this week"
            value={viewName}
            maxLength={40}
            onChange={(e) => setViewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") saveView();
            }}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setNaming(false)}>
              Cancel
            </Button>
            <Button disabled={!viewName.trim()} onClick={saveView}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {above?.(filters, query.data)}

      {selectable && selected.size ? (
        <div className="flex flex-wrap items-center gap-2 rounded-none border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
          <span className="font-medium">{selected.size} selected</span>
          <button type="button" className="text-muted-foreground hover:text-foreground" onClick={clear}>
            clear
          </button>
          <div className="ml-auto flex flex-wrap gap-2">{bulkActions!([...selected.values()], clear)}</div>
        </div>
      ) : null}

      {query.error ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : !query.isLoading && rows.length === 0 ? (
        (empty ?? <EmptyState title="Nothing here" description="Nothing matches. Try another search or filter." />)
      ) : (
        <Card className={cn("overflow-hidden p-0 transition-opacity", query.isPlaceholderData && "opacity-60")}>
          <Table>
            <TableHeader>
              <TableRow>
                {selectable ? (
                  <TableHead className="w-10">
                    <Checkbox
                      checked={allOnPage}
                      indeterminate={!allOnPage && someOnPage}
                      onCheckedChange={togglePage}
                      aria-label="Select this page"
                    />
                  </TableHead>
                ) : null}
                {shown.map((c) => (
                  <TableHead key={c.id} className={cn(c.hideBelow && HIDE[c.hideBelow], alignClass(c), c.className)}>
                    {c.sortKey ? (
                      <button
                        type="button"
                        onClick={() => sortBy(c.sortKey!)}
                        className={cn(
                          "inline-flex items-center gap-1 hover:text-foreground",
                          c.align === "right" && "flex-row-reverse",
                        )}
                      >
                        {c.header}
                        {ordering === c.sortKey ? (
                          <ArrowUp className="size-3.5" />
                        ) : ordering === `-${c.sortKey}` ? (
                          <ArrowDown className="size-3.5" />
                        ) : (
                          <ArrowUpDown className="size-3.5 opacity-40" />
                        )}
                      </button>
                    ) : (
                      c.header
                    )}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.isLoading
                ? Array.from({ length: 6 }).map((_, i) => (
                    <TableRow key={i}>
                      {selectable ? <TableCell /> : null}
                      {shown.map((c) => (
                        <TableCell key={c.id} className={cn(c.hideBelow && HIDE[c.hideBelow])}>
                          <Skeleton className="h-4 w-full max-w-40" />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                : rows.map((r, index) => {
                    const key = rowKey(r);
                    const can = !canSelect || canSelect(r);
                    return (
                      <TableRow
                        key={key}
                        ref={keys.itemRef(index)}
                        data-state={selected.has(key) ? "selected" : undefined}
                        className={cn(
                          onRowClick && "cursor-pointer",
                          keys.focused === index && "bg-primary/8 shadow-[inset_2px_0_0_var(--primary)]",
                        )}
                        onClick={() => onRowClick?.(r)}
                      >
                        {selectable ? (
                          <TableCell onClick={(e) => e.stopPropagation()}>
                            <Checkbox
                              checked={selected.has(key)}
                              disabled={!can}
                              onCheckedChange={() => toggleRow(r)}
                              aria-label="Select row"
                            />
                          </TableCell>
                        ) : null}
                        {shown.map((c) => (
                          <TableCell
                            key={c.id}
                            className={cn(c.hideBelow && HIDE[c.hideBelow], alignClass(c), c.className)}
                          >
                            {c.cell(r)}
                          </TableCell>
                        ))}
                      </TableRow>
                    );
                  })}
            </TableBody>
          </Table>
        </Card>
      )}

      {hasPrev || hasNext || rows.length >= pageSizes[0] ? (
        <div className="flex flex-wrap items-center justify-end gap-3 text-sm text-muted-foreground">
          {total > 0 ? (
            <span className="mr-auto tabular-nums">
              {(pageIndex * pageSize + 1).toLocaleString("en-IN")}–
              {Math.min((pageIndex + 1) * pageSize, total).toLocaleString("en-IN")} of {total.toLocaleString("en-IN")}
            </span>
          ) : null}
          <span className="flex items-center gap-2">
            Rows
            <Listbox
              items={Object.fromEntries(pageSizes.map((n) => [String(n), String(n)]))}
              value={String(pageSize)}
              onChange={(v) => update({ page_size: v === String(pageSizes[0]) ? undefined : (v as string) })}
              className="w-20"
            />
          </span>
          {numbered && pages > 1 ? <PageJump page={pageIndex + 1} pages={pages} onGo={goTo} /> : null}
          <div className="flex gap-1">
            {numbered && pages > 2 ? (
              <Button
                variant="outline"
                size="icon-sm"
                aria-label="First page"
                disabled={!hasPrev}
                onClick={() => goTo(1)}
              >
                <ChevronsLeft />
              </Button>
            ) : null}
            <Button variant="outline" size="sm" disabled={!hasPrev} onClick={() => goPage(-1)}>
              <ChevronLeft /> <span className="hidden sm:inline">Previous</span>
            </Button>
            <Button variant="outline" size="sm" disabled={!hasNext} onClick={() => goPage(1)}>
              <span className="hidden sm:inline">Next</span> <ChevronRight />
            </Button>
            {numbered && pages > 2 ? (
              <Button
                variant="outline"
                size="icon-sm"
                aria-label="Last page"
                disabled={!hasNext}
                onClick={() => goTo(pages)}
              >
                <ChevronsRight />
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** "Page [ 3 ] of 27" — type a number and press Enter to jump there. */
function PageJump({ page, pages, onGo }: { page: number; pages: number; onGo: (n: number) => void }) {
  const [text, setText] = useState(String(page));
  const [shown, setShown] = useState(page);
  if (shown !== page) {
    // the page changed from outside (next / previous): follow it
    setShown(page);
    setText(String(page));
  }
  const go = () => {
    const n = Number(text);
    if (Number.isFinite(n) && n >= 1) onGo(Math.min(n, pages));
    else setText(String(page));
  };
  return (
    <label className="flex items-center gap-1.5 tabular-nums">
      Page
      <input
        inputMode="numeric"
        aria-label="Go to page"
        value={text}
        onChange={(e) => setText(e.target.value.replace(/\D/g, "").slice(0, 6))}
        onBlur={go}
        onKeyDown={(e) => {
          if (e.key === "Enter") go();
        }}
        className="h-7 w-12 border border-input bg-transparent px-1.5 text-center text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
      />
      of {pages.toLocaleString("en-IN")}
    </label>
  );
}

/** A one-choice filter for `DataTable`: fixed choices, "All" first. */
export function FilterSelect({
  label,
  value,
  onChange,
  options,
  allLabel = "All",
}: {
  label: string;
  value: string | undefined;
  onChange: (v: string | undefined) => void;
  options: Record<string, string>;
  allLabel?: string;
}) {
  const items: Record<string, string> = {
    [ALL]: `${label}: ${allLabel}`,
    ...Object.fromEntries(Object.entries(options).map(([key, v]) => [key, `${label}: ${v}`])),
  };
  return (
    <Listbox
      items={items}
      value={value ?? ALL}
      onChange={(v) => onChange((v as string) || ALL)}
      className="w-auto min-w-36"
    />
  );
}

/**
 * A several-choice filter for `DataTable`: the value is the chosen keys joined
 * with commas (what the API's `status__in`-style params take). None = all.
 */
export function FilterMultiSelect({
  label,
  value,
  onChange,
  options,
  className,
}: {
  label: string;
  value: string | undefined;
  onChange: (v: string | undefined) => void;
  options: Record<string, string>;
  className?: string;
}) {
  const list = useMemo(() => Object.entries(options).map(([key, name]) => ({ key, name })), [options]);
  const picked = value && value !== ALL ? value.split(",") : [];
  return (
    <div className={cn("min-w-44", className)}>
      <AsyncSelect<{ key: string; name: string }>
        multiple
        options={list}
        value={list.filter((o) => picked.includes(o.key))}
        onChange={(next) => onChange(next.length ? next.map((o) => o.key).join(",") : ALL)}
        getValue={(o) => o.key}
        getLabel={(o) => o.name}
        placeholder={`${label}: All`}
        searchPlaceholder={`Find a ${label.toLowerCase()}`}
        className="min-h-8"
      />
    </div>
  );
}
