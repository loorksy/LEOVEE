import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";
import { useLocale } from "@/i18n/context";
import { IconButton } from "@/components/ui/IconButton";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const { t } = useLocale();
  const label = theme === "dark" ? t("theme.switchToLight") : t("theme.switchToDark");
  return (
    <IconButton data-testid="theme-toggle" aria-label={label} title={label} onClick={toggleTheme}>
      {theme === "dark" ? <Sun className="size-5 sm:size-4" /> : <Moon className="size-5 sm:size-4" />}
    </IconButton>
  );
}
