import { useEffect, useState } from "react";
import { THEME_CHANGED_EVENT, type Theme, getTheme, toggleTheme } from "@/api/themeStore";

export function useTheme(): { theme: Theme; toggleTheme: () => void } {
  const [theme, setThemeState] = useState<Theme>(getTheme);

  useEffect(() => {
    const handler = () => setThemeState(getTheme());
    window.addEventListener(THEME_CHANGED_EVENT, handler);
    window.addEventListener("storage", handler);
    return () => {
      window.removeEventListener(THEME_CHANGED_EVENT, handler);
      window.removeEventListener("storage", handler);
    };
  }, []);

  return { theme, toggleTheme };
}
