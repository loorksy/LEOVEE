import { type FormEvent, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { login } from "@/api/auth";
import { useLocale } from "@/i18n/context";
import { Card, CardContent } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";

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
    <div className="flex min-h-dvh items-center justify-center bg-background px-4 py-8">
      <Card className="w-full max-w-sm">
        <CardContent className="flex flex-col gap-4 p-4 sm:p-6">
          <form onSubmit={handleSubmit} className="flex flex-col gap-4" data-testid="login-form">
            <div className="flex items-center gap-2">
              <img src="/leovee.svg" alt={t("app.name")} className="h-8 w-8" />
              <span className="text-lg font-semibold text-foreground">{t("app.name")}</span>
            </div>
            <h1 className="text-xl font-semibold text-foreground">{t("auth.login")}</h1>
            <label className="flex flex-col gap-1 text-sm text-muted-foreground" htmlFor="login-email">
              {t("auth.email")}
              <Input
                id="login-email"
                data-testid="login-email"
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-muted-foreground" htmlFor="login-password">
              {t("auth.password")}
              <Input
                id="login-password"
                data-testid="login-password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
            <Button type="submit" data-testid="login-submit" disabled={submitting} className="w-full">
              {submitting ? t("auth.signingIn") : t("auth.login")}
            </Button>
            <p className="text-center text-xs text-muted-foreground">
              {t("auth.newHere")}{" "}
              <Link to="/signup" className="text-primary hover:underline">
                {t("auth.signup")}
              </Link>
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
