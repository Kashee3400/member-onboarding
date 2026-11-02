"use client";

import { Eye, EyeOff, type LucideIcon } from "lucide-react";
import { type ComponentProps, type ReactNode, useState } from "react";

import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
  InputGroupTextarea,
} from "@/components/ui/input-group";
import { cn } from "@/lib/utils";

type IconInputProps = Omit<ComponentProps<"input">, "prefix"> & {
  /** Icon at the start, saying what goes in the box. */
  leading?: LucideIcon;
  /** At the end: a unit ("hours", "₹"), a hint, or an InputGroupButton. */
  trailing?: ReactNode;
  groupClassName?: string;
};

/** The panel's text box: sharp edges, an icon for what it holds, an optional unit or action. */
export function IconInput({ leading: Leading, trailing, groupClassName, className, ...props }: IconInputProps) {
  return (
    <InputGroup className={groupClassName}>
      {Leading ? (
        <InputGroupAddon>
          <Leading />
        </InputGroupAddon>
      ) : null}
      <InputGroupInput className={className} {...props} />
      {trailing !== undefined && trailing !== null ? (
        <InputGroupAddon align="inline-end">{trailing}</InputGroupAddon>
      ) : null}
    </InputGroup>
  );
}

/** A secret or password box with a show / hide toggle at the end. */
export function SecretInput({ leading, ...props }: Omit<IconInputProps, "type" | "trailing">) {
  const [shown, setShown] = useState(false);
  return (
    <IconInput
      {...props}
      leading={leading}
      type={shown ? "text" : "password"}
      trailing={
        <InputGroupButton
          size="icon-xs"
          aria-label={shown ? "Hide" : "Show"}
          onClick={() => setShown((s) => !s)}
          // Hidden, not disabled: a disabled button would grey the whole box.
          className={props.value ? undefined : "invisible"}
        >
          {shown ? <EyeOff /> : <Eye />}
        </InputGroupButton>
      }
    />
  );
}

type IconTextareaProps = ComponentProps<"textarea"> & {
  leading?: LucideIcon;
  /** A line under the text: what the format is, how many items, whether it parses. */
  footer?: ReactNode;
  groupClassName?: string;
};

/** A multi-line box in the same frame, with a status line at the bottom. */
export function IconTextarea({ leading: Leading, footer, groupClassName, className, ...props }: IconTextareaProps) {
  return (
    <InputGroup className={groupClassName}>
      <InputGroupTextarea className={className} {...props} />
      {Leading || footer ? (
        <InputGroupAddon align="block-end" className={cn("border-t text-xs font-normal")}>
          {Leading ? <Leading className="size-3.5" /> : null}
          {footer}
        </InputGroupAddon>
      ) : null}
    </InputGroup>
  );
}
