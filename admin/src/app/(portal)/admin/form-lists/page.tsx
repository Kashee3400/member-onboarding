"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Pencil, Plus, RotateCcw, Archive } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Confirm } from "@/components/admin/confirm";
import { messageOf } from "@/components/admin/feedback";
import { FormDialog } from "@/components/admin/form-dialog";
import { Field } from "@/components/common/field";
import { PageHeader } from "@/components/common/page-header";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api/client";
import type { FormList } from "@/lib/types";

type Option = FormList["options"][number];
type Sent = { value?: string; label: string; label_hi: string; is_active: boolean };

const sent = (options: Option[]): Sent[] =>
  options.map((option) => ({
    value: option.value,
    label: option.label,
    label_hi: option.label_hi,
    is_active: option.active,
  }));

/** Each change saves at once: the list goes whole, in the order shown. */
function useSave(key: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (options: Sent[]) =>
      api<{ lists: FormList[] }>(`settings/form-lists/${key}`, { method: "PUT", body: { options } }),
    onSuccess: (saved) => {
      client.setQueryData(["form-lists"], saved);
      client.invalidateQueries({ queryKey: ["form-schema"] });
    },
  });
}

function OptionDialog({
  initial,
  onClose,
  onSave,
}: {
  initial: Option | null;
  onClose: () => void;
  onSave: (label: string, labelHi: string, done: () => void, fail: (error: unknown) => void) => void;
}) {
  const [label, setLabel] = useState(initial?.label ?? "");
  const [labelHi, setLabelHi] = useState(initial?.label_hi ?? "");
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const ready = label.trim() && labelHi.trim();

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!ready) return;
    setPending(true);
    onSave(label.trim(), labelHi.trim(), onClose, (failure) => {
      setPending(false);
      setError(failure);
    });
  };

  return (
    <FormDialog
      title={initial ? `Rename "${initial.label}"` : "Add an option"}
      description={
        initial
          ? "Forms that already hold this option show the new name, on screen and on the printed form."
          : "The facilitator's app shows the Hindi name; the portal and the printed form use the English one."
      }
      onClose={onClose}
      onSubmit={submit}
      error={error}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button type="submit" disabled={!ready || pending}>
            {pending ? "Saving…" : "Save option"}
          </Button>
        </>
      }
    >
      <Field label="English name" htmlFor="option-label">
        <Input
          id="option-label"
          maxLength={100}
          value={label}
          autoFocus
          onChange={(event) => setLabel(event.target.value)}
        />
      </Field>
      <Field label="Hindi name" htmlFor="option-label-hi">
        <Input id="option-label-hi" maxLength={100} value={labelHi} onChange={(event) => setLabelHi(event.target.value)} />
      </Field>
      {initial ? (
        <p className="text-xs text-muted-foreground">
          Saved as <code className="bg-muted px-1 font-mono">{initial.value}</code>, which never changes.
        </p>
      ) : null}
    </FormDialog>
  );
}

function ListCard({ list }: { list: FormList }) {
  const save = useSave(list.key);
  const [editing, setEditing] = useState<{ index: number | null } | null>(null);
  const options = list.options;

  const store = (next: Sent[], message: string, done?: () => void, fail?: (error: unknown) => void) =>
    save.mutate(next, {
      onSuccess: () => {
        toast.success(message);
        done?.();
      },
      onError: (error) => (fail ? fail(error) : toast.error(messageOf(error))),
    });

  const move = (index: number, by: number) => {
    const next = sent(options);
    [next[index], next[index + by]] = [next[index + by], next[index]];
    store(next, "Order saved.");
  };

  const setActive = (index: number, active: boolean) =>
    store(
      sent(options).map((option, other) => (other === index ? { ...option, is_active: active } : option)),
      active ? "Option back in use." : "Option retired.",
    );

  return (
    <Card className="gap-4 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-medium">{list.title}</h2>
          <p className="text-sm text-muted-foreground">
            {list.description}. Offered in this order. A retired option is no longer offered, but forms that already
            hold it keep it.
          </p>
        </div>
        <Button variant="outline" onClick={() => setEditing({ index: null })}>
          <Plus /> Add option
        </Button>
      </div>
      <ul className="divide-y border">
        {options.map((option, index) => (
          <li key={option.value} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5">
            <div className="min-w-0 flex-1">
              <p className={option.active ? "text-sm font-medium" : "text-sm font-medium text-muted-foreground"}>
                {option.label} <span className="font-normal text-muted-foreground">· {option.label_hi}</span>
              </p>
              <p className="font-mono text-xs text-muted-foreground">{option.value}</p>
            </div>
            {option.active ? null : <StatusBadge status="discarded" label="Retired" />}
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Move "${option.label}" up`}
                disabled={index === 0 || save.isPending}
                onClick={() => move(index, -1)}
              >
                <ArrowUp />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Move "${option.label}" down`}
                disabled={index === options.length - 1 || save.isPending}
                onClick={() => move(index, 1)}
              >
                <ArrowDown />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Rename "${option.label}"`}
                onClick={() => setEditing({ index })}
              >
                <Pencil />
              </Button>
              {option.active ? (
                <Confirm
                  trigger={
                    <Button variant="ghost" size="icon" aria-label={`Retire "${option.label}"`} disabled={save.isPending}>
                      <Archive />
                    </Button>
                  }
                  title="Retire this option?"
                  description={`"${option.label}" will no longer be offered on new forms. Forms that already hold it keep it, and it can be brought back.`}
                  action="Retire"
                  onConfirm={() => setActive(index, false)}
                />
              ) : (
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Bring "${option.label}" back`}
                  disabled={save.isPending}
                  onClick={() => setActive(index, true)}
                >
                  <RotateCcw />
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>
      {editing ? (
        <OptionDialog
          initial={editing.index === null ? null : options[editing.index]}
          onClose={() => setEditing(null)}
          onSave={(label, labelHi, done, fail) => {
            const next =
              editing.index === null
                ? [...sent(options), { label, label_hi: labelHi, is_active: true }]
                : sent(options).map((option, index) =>
                    index === editing.index ? { ...option, label, label_hi: labelHi } : option,
                  );
            store(next, editing.index === null ? "Option added." : "Option renamed.", done, fail);
          }}
        />
      ) : null}
    </Card>
  );
}

export default function FormListsPage() {
  const state = useQuery({
    queryKey: ["form-lists"],
    queryFn: () => api<{ lists: FormList[] }>("settings/form-lists"),
  });
  const [chosen, setChosen] = useState<string | null>(null);
  const lists = state.data?.lists ?? [];
  const list = lists.find((item) => item.key === chosen) ?? lists[0];

  return (
    <>
      <PageHeader
        title="Form Lists"
        description="The choices the membership form offers. Rename, reorder, add or retire them; saved forms keep their answers."
      />
      {state.error ? (
        <ErrorState error={state.error} onRetry={() => state.refetch()} />
      ) : list ? (
        <>
          <Tabs value={list.key} onValueChange={(next) => setChosen(String(next))}>
            <TabsList className="h-auto flex-wrap">
              {lists.map((item) => (
                <TabsTrigger key={item.key} value={item.key}>
                  {item.title}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <ListCard key={list.key} list={list} />
        </>
      ) : (
        <ListSkeleton rows={6} />
      )}
    </>
  );
}
