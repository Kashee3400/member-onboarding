"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown, Loader2, Plus, Search, X } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { api, cursorOf, type Page } from "@/lib/api/client";
import { cn } from "@/lib/utils";

/**
 * A searchable select for lists of any size (Select2-style).
 *
 * - Loads nothing until it is opened; then fetches page by page as you scroll.
 * - Searches on the server (`?q=`), debounced; an older search is cancelled.
 * - Works with the API's cursor pages (`{results, next}`) out of the box via
 *   `endpoint`, any other source via `fetchPage`, or a small fixed list via `options`.
 * - Single or multiple (chips), clearable, keyboard driven, can create a new option.
 *
 * The value is the option object itself, so its label shows without fetching
 * it again; pass the object you got from the API (or build one) as `value`.
 */

export type FetchPage<T> = (args: {
  search: string;
  cursor: string | null;
  signal: AbortSignal;
}) => Promise<{ items: T[]; next: string | null }>;

type Common<T> = {
  /** DRF endpoint returning `Page<T>`, e.g. "ops/store/sellers/all". */
  endpoint?: string;
  /** Extra query params (filters). Changing them starts the list over. */
  params?: Record<string, string | number | boolean | undefined | null>;
  /** Any other source. Wins over `endpoint`. */
  fetchPage?: FetchPage<T>;
  /** A fixed list, filtered here. For small lists only. */
  options?: T[];
  getValue: (option: T) => string;
  getLabel: (option: T) => string;
  /** A second, quieter line under the label. */
  getDescription?: (option: T) => ReactNode;
  /** Custom row; the default is label + description. */
  renderOption?: (option: T, state: { selected: boolean; active: boolean; search: string }) => ReactNode;
  isOptionDisabled?: (option: T) => boolean | string;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyText?: string;
  /** Don't search before this many characters (still lists on open with 0). */
  minSearch?: number;
  debounceMs?: number;
  pageSize?: number;
  disabled?: boolean;
  clearable?: boolean;
  /** Shows "Add “…”" for a search with no exact match. */
  onCreate?: (search: string) => Promise<T | void> | T | void;
  createLabel?: (search: string) => string;
  invalid?: boolean;
  /**
   * Dependent selects: when any of these change (e.g. the chosen seller), the
   * value is cleared, because the old choice may not belong any more.
   */
  resetOn?: unknown[];
  id?: string;
  name?: string;
  onBlur?: () => void;
  className?: string;
  /** Width of the dropdown; defaults to the trigger's. */
  popoverClassName?: string;
};

type Single<T> = Common<T> & { multiple?: false; value: T | null; onChange: (value: T | null) => void };
type Multiple<T> = Common<T> & {
  multiple: true;
  value: T[];
  onChange: (value: T[]) => void;
  maxSelected?: number;
};

export type AsyncSelectProps<T> = Single<T> | Multiple<T>;

function useDebounced<V>(value: V, ms: number): V {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function AsyncSelect<T>(props: AsyncSelectProps<T>) {
  const {
    endpoint,
    params,
    fetchPage,
    options,
    getValue,
    getLabel,
    getDescription,
    renderOption,
    isOptionDisabled,
    placeholder = "Select…",
    searchPlaceholder = "Search…",
    emptyText = "Nothing found",
    minSearch = 0,
    debounceMs = 300,
    pageSize = 20,
    disabled,
    clearable = true,
    onCreate,
    createLabel = (s) => `Add “${s}”`,
    invalid,
    id,
    name,
    onBlur,
    className,
    popoverClassName,
    resetOn,
  } = props;

  const listId = useId();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [active, setActive] = useState(0);
  const [creating, setCreating] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const sentinel = useRef<HTMLDivElement>(null);
  const term = useDebounced(search.trim(), debounceMs);

  // Clear the value when what it depends on changes (not on first render).
  const resetKey = JSON.stringify(resetOn ?? []);
  const lastReset = useRef(resetKey);
  useEffect(() => {
    if (lastReset.current === resetKey) return;
    lastReset.current = resetKey;
    if (props.multiple) {
      if (props.value.length) props.onChange([]);
    } else if (props.value) props.onChange(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey]);
  const searchable = term.length >= minSearch ? term : "";

  const raw = props.value;
  const selected: T[] = useMemo(() => (Array.isArray(raw) ? raw : raw ? [raw] : []), [raw]);
  const selectedKeys = useMemo(() => new Set(selected.map(getValue)), [selected, getValue]);

  const remote = !options;
  const query = useInfiniteQuery({
    queryKey: ["select", endpoint ?? "custom", params ?? {}, searchable],
    enabled: open && remote && (!!endpoint || !!fetchPage),
    initialPageParam: null as string | null,
    staleTime: 30_000,
    queryFn: async ({ pageParam, signal }) => {
      if (fetchPage) return fetchPage({ search: searchable, cursor: pageParam, signal });
      const page = await api<Page<T>>(endpoint!, {
        query: { ...params, q: searchable || undefined, cursor: pageParam ?? undefined, page_size: pageSize },
        signal,
      });
      return { items: page.results, next: cursorOf(page.next) };
    },
    getNextPageParam: (last) => last.next,
  });

  const items: T[] = useMemo(() => {
    if (options) {
      const q = searchable.toLowerCase();
      return q ? options.filter((o) => getLabel(o).toLowerCase().includes(q)) : options;
    }
    return query.data?.pages.flatMap((p) => p.items) ?? [];
  }, [options, searchable, getLabel, query.data]);

  const exact = items.some((o) => getLabel(o).toLowerCase() === search.trim().toLowerCase());
  const showCreate = !!onCreate && search.trim().length > 0 && !exact && !query.isFetching;
  const rows = items.length + (showCreate ? 1 : 0);

  // Load the next page when the bottom of the list comes into view.
  useEffect(() => {
    const el = sentinel.current;
    if (!open || !el || !remote) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage();
      },
      { root: listRef.current, rootMargin: "120px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [open, remote, query, items.length]);

  // Keep the highlighted row visible.
  useEffect(() => {
    listRef.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const changeOpen = (next: boolean) => {
    setOpen(next);
    if (!next) {
      setSearch("");
      setActive(0);
      onBlur?.();
    }
  };

  const toggle = useCallback(
    (option: T) => {
      if (isOptionDisabled?.(option)) return;
      const key = getValue(option);
      if (props.multiple) {
        const has = selectedKeys.has(key);
        if (!has && props.maxSelected && props.value.length >= props.maxSelected) return;
        props.onChange(has ? props.value.filter((o) => getValue(o) !== key) : [...props.value, option]);
      } else {
        props.onChange(option);
        changeOpen(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [props, selectedKeys, getValue, isOptionDisabled],
  );

  const create = async () => {
    if (!onCreate) return;
    setCreating(true);
    try {
      const made = await onCreate(search.trim());
      if (made) toggle(made);
      setSearch("");
      void query.refetch();
    } finally {
      setCreating(false);
    }
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, Math.max(rows - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Home") {
      setActive(0);
    } else if (e.key === "End") {
      setActive(Math.max(rows - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (active < items.length) toggle(items[active]);
      else if (showCreate) void create();
    } else if (e.key === "Backspace" && !search && props.multiple && props.value.length) {
      props.onChange(props.value.slice(0, -1));
    }
  };

  const clear = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (props.multiple) props.onChange([]);
    else props.onChange(null);
  };

  const atMax = props.multiple && !!props.maxSelected && props.value.length >= props.maxSelected;

  return (
    <Popover open={open} onOpenChange={changeOpen}>
      <PopoverTrigger
        nativeButton={false}
        disabled={disabled}
        render={
          <div
            id={id}
            role="combobox"
            tabIndex={disabled ? -1 : 0}
            aria-expanded={open}
            aria-controls={listId}
            aria-haspopup="listbox"
            aria-invalid={invalid || undefined}
            aria-disabled={disabled || undefined}
            className={cn(
              "flex min-h-9 w-full cursor-pointer items-center gap-1.5 rounded-none border border-input bg-transparent px-2.5 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none",
              "focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
              "aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:bg-input/30",
              disabled && "pointer-events-none cursor-not-allowed opacity-50",
              className,
            )}
          />
        }
      >
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1">
          {selected.length === 0 ? (
            <span className="truncate text-muted-foreground">{placeholder}</span>
          ) : props.multiple ? (
            props.value.map((o) => (
              <span
                key={getValue(o)}
                className="inline-flex max-w-full items-center gap-1 rounded bg-secondary px-1.5 py-0.5 text-xs"
              >
                <span className="truncate">{getLabel(o)}</span>
                <button
                  type="button"
                  aria-label={`Remove ${getLabel(o)}`}
                  className="rounded-sm opacity-60 hover:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggle(o);
                  }}
                >
                  <X className="size-3" />
                </button>
              </span>
            ))
          ) : (
            <span className="truncate">{getLabel(selected[0])}</span>
          )}
        </div>
        {clearable && selected.length && !disabled ? (
          <button
            type="button"
            aria-label="Clear"
            onClick={clear}
            className="rounded-sm p-0.5 text-muted-foreground hover:text-foreground"
          >
            <X className="size-3.5" />
          </button>
        ) : null}
        <ChevronsUpDown className="size-4 shrink-0 text-muted-foreground" />
        {name ? <input type="hidden" name={name} value={selected.map(getValue).join(",")} /> : null}
      </PopoverTrigger>
      <PopoverContent align="start" className={cn("w-(--anchor-width) min-w-64 gap-0 p-0", popoverClassName)}>
        <div className="flex items-center gap-2 border-b px-2.5">
          <Search className="size-4 shrink-0 text-muted-foreground" />
          <input
            autoFocus
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setActive(0);
            }}
            onKeyDown={onKey}
            placeholder={searchPlaceholder}
            aria-controls={listId}
            aria-activedescendant={rows ? `${listId}-${active}` : undefined}
            className="h-9 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          {query.isFetching && !query.isFetchingNextPage ? (
            <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />
          ) : null}
        </div>
        <div
          ref={listRef}
          id={listId}
          role="listbox"
          aria-multiselectable={props.multiple || undefined}
          className="max-h-72 overflow-y-auto p-1"
        >
          {minSearch > 0 && search.trim().length > 0 && search.trim().length < minSearch ? (
            <p className="px-2 py-6 text-center text-sm text-muted-foreground">Type at least {minSearch} characters</p>
          ) : query.isError ? (
            <div className="px-2 py-6 text-center text-sm">
              <p className="text-destructive">Couldn&apos;t load the list.</p>
              <button type="button" className="mt-1 text-primary underline" onClick={() => query.refetch()}>
                Try again
              </button>
            </div>
          ) : query.isLoading && remote ? (
            <div className="space-y-1 p-1">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-8 animate-pulse rounded bg-muted" />
              ))}
            </div>
          ) : (
            <>
              {items.map((o, i) => {
                const key = getValue(o);
                const isSel = selectedKeys.has(key);
                const why = isOptionDisabled?.(o);
                const off = !!why || (atMax && !isSel);
                return (
                  <div
                    key={key}
                    id={`${listId}-${i}`}
                    data-index={i}
                    role="option"
                    aria-selected={isSel}
                    aria-disabled={off || undefined}
                    title={typeof why === "string" ? why : undefined}
                    onMouseMove={() => setActive(i)}
                    onClick={() => !off && toggle(o)}
                    className={cn(
                      "flex cursor-pointer items-start gap-2 rounded-none px-2 py-1.5 text-sm select-none",
                      i === active && "bg-accent text-accent-foreground",
                      off && "cursor-not-allowed opacity-50",
                    )}
                  >
                    <Check className={cn("mt-0.5 size-4 shrink-0", isSel ? "opacity-100" : "opacity-0")} />
                    <div className="min-w-0 flex-1">
                      {renderOption ? (
                        renderOption(o, { selected: isSel, active: i === active, search: searchable })
                      ) : (
                        <>
                          <p className="truncate">
                            <Highlight text={getLabel(o)} search={searchable} />
                          </p>
                          {getDescription ? (
                            <p className="truncate text-xs text-muted-foreground">{getDescription(o)}</p>
                          ) : null}
                          {typeof why === "string" ? <p className="text-xs text-muted-foreground">{why}</p> : null}
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
              {showCreate ? (
                <div
                  id={`${listId}-${items.length}`}
                  data-index={items.length}
                  role="option"
                  aria-selected={false}
                  onMouseMove={() => setActive(items.length)}
                  onClick={() => void create()}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 rounded-none px-2 py-1.5 text-sm text-primary",
                    active === items.length && "bg-accent",
                  )}
                >
                  {creating ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
                  {createLabel(search.trim())}
                </div>
              ) : null}
              {!items.length && !showCreate ? (
                <p className="px-2 py-6 text-center text-sm text-muted-foreground">{emptyText}</p>
              ) : null}
              {remote ? <div ref={sentinel} className="h-1" /> : null}
              {query.isFetchingNextPage ? (
                <p className="flex items-center justify-center gap-1.5 py-2 text-xs text-muted-foreground">
                  <Loader2 className="size-3.5 animate-spin" /> Loading more…
                </p>
              ) : null}
            </>
          )}
        </div>
        {props.multiple && (props.value.length || props.maxSelected) ? (
          <div className="flex items-center justify-between border-t px-2.5 py-1.5 text-xs text-muted-foreground">
            <span>
              {props.value.length} selected{props.maxSelected ? ` of ${props.maxSelected}` : ""}
            </span>
            <button type="button" className="hover:text-foreground" onClick={() => changeOpen(false)}>
              Done
            </button>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}

/** Bolds the part of `text` that matches the search. */
function Highlight({ text, search }: { text: string; search: string }) {
  if (!search) return <>{text}</>;
  const at = text.toLowerCase().indexOf(search.toLowerCase());
  if (at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <mark className="rounded-sm bg-primary/15 font-medium text-inherit">{text.slice(at, at + search.length)}</mark>
      {text.slice(at + search.length)}
    </>
  );
}
