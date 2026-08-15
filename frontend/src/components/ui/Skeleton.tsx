import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

/** Loading placeholder — motion limited to a state-feedback pulse (DESIGN.md §6). */
export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  );
}
