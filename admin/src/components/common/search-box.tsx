"use client";

import { Search, X } from "lucide-react";
import { useEffect, useState } from "react";

import { IconInput } from "@/components/common/form-input";
import { InputGroupButton } from "@/components/ui/input-group";

/** A search field that tells its parent once typing pauses. */
export function SearchBox({
  value,
  onChange,
  placeholder = "Search",
  className = "w-full sm:w-72",
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}) {
  const [text, setText] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => {
      if (text.trim() !== value) onChange(text.trim());
    }, 350);
    return () => clearTimeout(t);
  }, [text, value, onChange]);

  return (
    <IconInput
      groupClassName={className}
      leading={Search}
      type="search"
      value={text}
      onChange={(e) => setText(e.target.value)}
      placeholder={placeholder}
      // "/" anywhere jumps here (components/shell/command-search.tsx).
      data-page-search=""
      className="[&::-webkit-search-cancel-button]:hidden"
      trailing={
        text ? (
          <InputGroupButton
            size="icon-xs"
            aria-label="Clear search"
            onClick={() => {
              setText("");
              onChange("");
            }}
          >
            <X />
          </InputGroupButton>
        ) : undefined
      }
    />
  );
}
