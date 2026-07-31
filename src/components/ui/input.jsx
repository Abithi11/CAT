import React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef(({ className, ...props }, ref) => (
  <input
    ref={ref}
    className={cn(
      "flex h-11 w-full rounded-tag border border-rig-600 bg-rig-900 px-3.5 text-sm text-rig-50 placeholder:text-rig-500 focus-visible:outline-none focus-visible:border-signal transition-colors",
      className
    )}
    {...props}
  />
));
Input.displayName = "Input";
