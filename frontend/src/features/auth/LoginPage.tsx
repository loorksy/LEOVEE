import { type FormEvent, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { login } from "@/api/auth";
import { useLocale } from "@/i18n/context";

type LocationState = { from?: { pathname?: string } };

export function LoginPage() {
  const { t } = useLocale();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      const state = location.state as LocationState | null;
      navigate(state?.from?.pathname ?? "/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("auth.error.loginFailed"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-leovee-surface px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-lg border border-slate-800 bg-leovee-panel p-8"
      >
        <div className="mb-6 flex items-center gap-2">
          <img src="/leovee.svg" alt={t("app.name")} className="h-8 w-8" />
          <span className="text-lg font-semibold text-white">{t("app.name")}</span>
        </div>
        <h1 className="mb-4 text-xl font-semibold text-slate-100">{t("auth.login")}</h1>
        <label className="mb-3 block text-sm text-slate-300" htmlFor="login-email">
          {t("auth.email")}
          <input
            id="login-email"
            data-testid="login-email"
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100"
          />
        </label>
        <label className="mb-4 block text-sm text-slate-300" htmlFor="login-password">
          {t("auth.password")}
          <input
            id="login-password"
            data-testid="login-password"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100"
          />
        </label>
        {error && (
          <p role="alert" className="mb-4 text-sm text-red-400">
            {error}
          </p>
        )}
        <button
          type="submit"
          data-testid="login-submit"
          disabled={submitting}
          className="w-full rounded bg-leovee-accent px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
        >
          {submitting ? t("auth.signingIn") : t("auth.login")}
        </button>
        <p className="mt-4 text-center text-xs text-slate-500">
          {t("auth.newHere")}{" "}
          <Link to="/signup" className="text-leovee-accent hover:underline">
            {t("auth.signup")}
          </Link>
        </p>
      </form>
    </div>
  );
}
