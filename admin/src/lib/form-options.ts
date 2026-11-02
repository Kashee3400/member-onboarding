import type { FormChoice } from "@/lib/types";

/**
 * The label for a saved choice. Retired choices are looked up too, so an older form
 * still reads; a value no list knows (such as a nominee relation typed before it was
 * a list) shows as it was typed.
 */
export function choiceLabel(
  value: unknown,
  options: FormChoice[] | undefined,
  retired: FormChoice[] | undefined = undefined,
): string {
  const text = value === undefined || value === null ? "" : String(value);
  return [...(options ?? []), ...(retired ?? [])].find((option) => option.value === text)?.label ?? text;
}
