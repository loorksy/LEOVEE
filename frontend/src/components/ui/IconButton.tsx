import { type ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/cn";

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Required — an icon-only control has no other accessible name. */
  "aria-label": string;
}

/** A bare icon control: 44px touch target down to `sm:` 40px, focus-visible ring. */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ className, type = "button", ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(
        "inline-flex size-11 shrink-0 items-center justify-center rounded-lg text-muted-foreground outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 sm:size-9",
        className,
      )}
      {...props}
    />
  ),
);
IconButton.displayName = "IconButton";
