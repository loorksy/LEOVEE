import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { signup } from "@/api/auth";
import { useLocale } from "@/i18n/context";
import { Card, CardContent } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";

export function SignupPage() {
  const { t } = useLocale();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await signup(email, password, organizationName || undefined);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("auth.error.signupFailed"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-background px-4 py-8">
      <Card className="w-full max-w-sm">
        <CardContent className="flex flex-col gap-4 p-4 sm:p-6">
          <form onSubmit={handleSubmit} className="flex flex-col gap-4" data-testid="signup-form">
            <div className="flex items-center gap-2">
              <img src="/leovee.svg" alt={t("app.name")} className="h-8 w-8" />
              <span className="text-lg font-semibold text-foreground">{t("app.name")}</span>
            </div>
            <h1 className="text-xl font-semibold text-foreground">{t("auth.signup")}</h1>
            <label className="flex flex-col gap-1 text-sm text-muted-foreground" htmlFor="signup-org">
              {t("auth.orgName")}
              <Input
                id="signup-org"
                data-testid="signup-org"
                type="text"
                autoComplete="organization"
                value={organizationName}
                onChange={(event) => setOrganizationName(event.target.value)}
                placeholder={t("auth.orgPlaceholder")}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-muted-foreground" htmlFor="signup-email">
              {t("auth.email")}
              <Input
                id="signup-email"
                data-testid="signup-email"
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-muted-foreground" htmlFor="signup-password">
              {t("auth.password")}
              <Input
                id="signup-password"
                data-testid="signup-password"
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
            <Button type="submit" data-testid="signup-submit" disabled={submitting} className="w-full">
              {submitting ? t("auth.creatingAccount") : t("auth.signup")}
            </Button>
            <p className="text-center text-xs text-muted-foreground">
              {t("auth.haveAccount")}{" "}
              <Link to="/login" className="text-primary hover:underline">
                {t("auth.login")}
              </Link>
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
