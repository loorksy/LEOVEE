import { type ButtonHTMLAttributes, forwardRef } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

/**
 * The one accent this product spends on actions — monochrome (DESIGN.md §2:
 * "no purple", "color is never decoration"). Every variant here reuses a
 * semantic token, never a raw hex or an ad-hoc Tailwind color name.
 *
 * Sizes follow the 44px mobile / 40px pointer touch-target split (DESIGN.md
 * §8): `default` and `lg` meet 44px unprefixed, `sm` is for dense toolbars
 * that are never someone's only way to reach an action.
 */
const buttonVariants = cva(
  "inline-flex shrink-0 select-none items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-sm font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-primary text-primary-foreground hover:bg-primary/90",
        outline: "border border-border bg-transparent text-foreground hover:bg-muted",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "bg-transparent text-foreground hover:bg-muted",
        destructive: "bg-destructive/10 text-destructive hover:bg-destructive/20",
        link: "bg-transparent text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-11 px-4 sm:h-9 sm:px-3.5",
        sm: "h-9 px-3 text-xs sm:h-8",
        lg: "h-11 px-5",
        icon: "size-11 sm:size-9",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, type = "button", ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  ),
);
Button.displayName = "Button";
