import React from "react";
import { cn } from "@/lib/utils";

export function Label({ className, ...props }) {
  return (
    <label
      className={cn(
        "text-xs font-display font-semibold uppercase tracking-widest text-rig-400",
        className
      )}
      {...props}
    />
  );
}
