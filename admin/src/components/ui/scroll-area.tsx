"use client";

import * as React from "react";
import { ScrollArea as ScrollAreaPrimitive } from "@base-ui/react/scroll-area";
import { cn } from "@/lib/utils";

/**
 * A scroll container with thin overlay scrollbars on both axes. They stay
 * faint, show up while you hover or scroll, and widen + turn brand gold under
 * the pointer — the same look as the panel's native scrollbars.
 */
function ScrollArea({
  className,
  children,
  orientation = "both",
  ...props
}: ScrollAreaPrimitive.Root.Props & { orientation?: "vertical" | "horizontal" | "both" }) {
  return (
    <ScrollAreaPrimitive.Root data-slot="scroll-area" className={cn("group/scroll relative", className)} {...props}>
      <ScrollAreaPrimitive.Viewport
        data-slot="scroll-area-viewport"
        className="size-full rounded-[inherit] transition-[color,box-shadow] outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-1"
      >
        {children}
      </ScrollAreaPrimitive.Viewport>
      {orientation !== "horizontal" ? <ScrollBar orientation="vertical" /> : null}
      {orientation !== "vertical" ? <ScrollBar orientation="horizontal" /> : null}
      <ScrollAreaPrimitive.Corner />
    </ScrollAreaPrimitive.Root>
  );
}

function ScrollBar({ className, orientation = "vertical", ...props }: ScrollAreaPrimitive.Scrollbar.Props) {
  return (
    <ScrollAreaPrimitive.Scrollbar
      data-slot="scroll-area-scrollbar"
      data-orientation={orientation}
      orientation={orientation}
      className={cn(
        "group/bar absolute z-10 flex touch-none p-0.5 opacity-0 transition-[opacity,width,height] duration-200 select-none",
        // shown while the pointer is over the area or it is being scrolled
        "group-hover/scroll:opacity-100 data-[scrolling]:opacity-100 data-[hovering]:opacity-100",
        "data-[orientation=vertical]:top-0 data-[orientation=vertical]:right-0 data-[orientation=vertical]:bottom-0 data-[orientation=vertical]:w-2 data-[orientation=vertical]:hover:w-2.5",
        "data-[orientation=horizontal]:right-0 data-[orientation=horizontal]:bottom-0 data-[orientation=horizontal]:left-0 data-[orientation=horizontal]:h-2 data-[orientation=horizontal]:flex-col data-[orientation=horizontal]:hover:h-2.5",
        className,
      )}
      {...props}
    >
      <ScrollAreaPrimitive.Thumb
        data-slot="scroll-area-thumb"
        className="relative flex-1 rounded-full bg-(--scrollbar-thumb) transition-colors duration-150 group-hover/bar:bg-(--scrollbar-thumb-hover) data-[orientation=horizontal]:h-full data-[orientation=vertical]:w-full"
      />
    </ScrollAreaPrimitive.Scrollbar>
  );
}

export { ScrollArea, ScrollBar };
