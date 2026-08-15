import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * One title grammar for every page — DESIGN.md §3 sizes page titles
 * `text-lg font-semibold` (density is a feature, not a compromise). Actions
 * wrap onto their own row on narrow screens rather than crowding the title.
 */
export function PageHeader({
  title,
  description,
  actions,
  testId,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  testId?: string;
  className?: string;
}) {
  return (
    <header
      className={cn(
        "flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between",
        className,
      )}
    >
      <div className="min-w-0">
        <h1
          data-testid={testId}
          className="truncate text-lg font-semibold text-foreground sm:text-xl"
        >
          {title}
        </h1>
        {description && (
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
