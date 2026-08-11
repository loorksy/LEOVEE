import { useEffect, useState } from "react";
import { AUTH_CHANGED_EVENT, isAuthenticated as checkAuthenticated } from "@/api/authStore";

export function useAuth(): { isAuthenticated: boolean } {
  const [authenticated, setAuthenticated] = useState(checkAuthenticated);

  useEffect(() => {
    const handler = () => setAuthenticated(checkAuthenticated());
    window.addEventListener(AUTH_CHANGED_EVENT, handler);
    window.addEventListener("storage", handler);
    return () => {
      window.removeEventListener(AUTH_CHANGED_EVENT, handler);
      window.removeEventListener("storage", handler);
    };
  }, []);

  return { isAuthenticated: authenticated };
}
