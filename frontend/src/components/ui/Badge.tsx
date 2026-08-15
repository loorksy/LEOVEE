import type { HTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

/**
 * `rounded-full border px-2 py-0.5 text-[11px]` — DESIGN.md §4. Tradability
 * chips route through the direction/warning/muted tones here (§2): `now` →
 * buy, `soon` → warning, `watch_only` → muted. `rejected` is never rendered
 * as a card at all — that rule lives at the call site, not in this component.
 */
const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium",
  {
    variants: {
      variant: {
        neutral: "border-border bg-transparent text-muted-foreground",
        buy: "border-buy/30 bg-buy/10 text-buy",
        sell: "border-sell/30 bg-sell/10 text-sell",
        warning: "border-warning/30 bg-warning/10 text-warning",
        info: "border-info/30 bg-info/10 text-info",
        destructive: "border-destructive/30 bg-destructive/10 text-destructive",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  },
);

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />;
}
