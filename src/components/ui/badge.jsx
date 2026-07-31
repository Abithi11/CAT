import React from "react";
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-tag px-2.5 py-1 text-[11px] font-display font-semibold uppercase tracking-widest",
  {
    variants: {
      variant: {
        ok: "bg-ok/15 text-ok border border-ok/30",
        warn: "bg-signal/15 text-signal border border-signal/30",
        danger: "bg-rust/15 text-rust border border-rust/30",
        neutral: "bg-rig-700 text-rig-300 border border-rig-600",
      },
    },
    defaultVariants: { variant: "neutral" },
  }
);

export function Badge({ className, variant, ...props }) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
