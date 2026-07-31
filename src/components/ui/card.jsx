import React from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }) {
  return <div className={cn("tag-plate p-6", className)} {...props} />;
}

export function CardHeader({ className, ...props }) {
  return <div className={cn("mb-4 space-y-1", className)} {...props} />;
}

export function CardTitle({ className, ...props }) {
  return (
    <h3
      className={cn(
        "font-display text-xl font-semibold uppercase tracking-wide text-rig-50",
        className
      )}
      {...props}
    />
  );
}

export function CardDescription({ className, ...props }) {
  return (
    <p className={cn("text-sm text-rig-400", className)} {...props} />
  );
}

export function CardContent({ className, ...props }) {
  return <div className={cn("", className)} {...props} />;
}
