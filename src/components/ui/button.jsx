import React from "react";
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-tag font-display font-semibold tracking-wide uppercase text-sm transition-colors focus-visible:outline-none disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        primary:
          "bg-signal text-rig-950 hover:bg-signal-600 shadow-rivet",
        secondary:
          "bg-rig-800 text-rig-50 border border-rig-600 hover:border-signal/60 hover:text-signal",
        ghost: "text-rig-200 hover:text-signal hover:bg-rig-800",
        danger: "bg-rust text-rig-50 hover:bg-rust-600",
      },
      size: {
        default: "h-11 px-5",
        sm: "h-9 px-3 text-xs",
        lg: "h-14 px-8 text-base",
        icon: "h-11 w-11",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  }
);

export const Button = React.forwardRef(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  )
);
Button.displayName = "Button";
