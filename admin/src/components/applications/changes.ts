import { choiceLabel } from "@/lib/form-options";
import type { ApplicationDetail, ApplicationDocument, FormSchema } from "@/lib/types";

export type Change = { path: string; section: string; label: string; before: string; after: string };

/** What a resubmission changed since the one before, so a reviewer reads only that. */
export type Changes = {
  /** The submission compared against, or null for a first submission. */
  since: number | null;
  fields: Change[];
  byPath: Map<string, Change>;
  documents: Set<string>;
  /** Fields the last rejection marked that are still as they were. */
  untouched: string[];
};

const NONE: Changes = { since: null, fields: [], byPath: new Map(), documents: new Set(), untouched: [] };

const text = (value: unknown) => {
  if (value === undefined || value === null || value === "") return "";
  if (value === true) return "Yes";
  if (value === false) return "No";
  return String(value);
};

const familyText = (family: ApplicationDetail["data"]["family"]) =>
  (family ?? []).map((person) => `${person.name} (${person.relation}, ${person.age})`).join(", ");

export function changesOf(
  application: ApplicationDetail,
  schema: FormSchema,
  documents: ApplicationDocument[],
): Changes {
  const [current, previous] = application.revisions;
  if (!current || !previous) return NONE;

  const fields: Change[] = [];
  for (const section of schema.sections) {
    const before = previous.data[section.key] ?? {};
    const after = current.data[section.key] ?? {};
    for (const field of section.fields) {
      const was = text(before[field.key]);
      const now = text(after[field.key]);
      if (was === now) continue;
      const label = (option: string) => choiceLabel(option, field.options, field.retired_options);
      fields.push({
        path: `${section.key}.${field.key}`,
        section: section.key,
        label: field.label,
        before: label(was),
        after: label(now),
      });
    }
  }
  const numbers = [
    ["applicant.aadhaar_number", "applicant", "Aadhaar", previous.aadhaar_last4, current.aadhaar_last4],
    ["bank.account_number", "bank", "Bank account", previous.account_last4, current.account_last4],
  ] as const;
  for (const [path, section, label, was, now] of numbers) {
    if (was !== now) fields.push({ path, section, label, before: was && `…${was}`, after: now && `…${now}` });
  }
  const familyBefore = familyText(previous.data.family);
  const familyAfter = familyText(current.data.family);
  if (familyBefore !== familyAfter) {
    fields.push({ path: "family", section: "family", label: "Household members", before: familyBefore, after: familyAfter });
  }

  // A file sent again after the earlier submission is a new one to look at.
  const documentsChanged = new Set(
    documents.filter((item) => item.created_at > previous.submitted_at).map((item) => item.document_type),
  );
  const byPath = new Map(fields.map((change) => [change.path, change]));
  const lastRejection = application.decisions
    .filter((item) => item.decision === "rejected" && item.revision === previous.number)
    .at(-1);
  return {
    since: previous.number,
    fields,
    byPath,
    documents: documentsChanged,
    untouched: (lastRejection?.rejected_fields ?? []).filter((path) => !byPath.has(path)),
  };
}
