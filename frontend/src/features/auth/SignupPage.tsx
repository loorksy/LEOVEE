import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { signup } from "@/api/auth";

export function SignupPage() {
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
      setError(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-leovee-surface px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-lg border border-slate-800 bg-leovee-panel p-8"
        data-testid="signup-form"
      >
        <div className="mb-6 flex items-center gap-2">
          <img src="/leovee.svg" alt="Leovee" className="h-8 w-8" />
          <span className="text-lg font-semibold text-white">Leovee</span>
        </div>
        <h1 className="mb-4 text-xl font-semibold text-slate-100">Create account</h1>
        <label className="mb-3 block text-sm text-slate-300" htmlFor="signup-org">
          Workspace / organization name
          <input
            id="signup-org"
            type="text"
            autoComplete="organization"
            value={organizationName}
            onChange={(event) => setOrganizationName(event.target.value)}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100"
            placeholder="My desk"
          />
        </label>
        <label className="mb-3 block text-sm text-slate-300" htmlFor="signup-email">
          Email
          <input
            id="signup-email"
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100"
          />
        </label>
        <label className="mb-4 block text-sm text-slate-300" htmlFor="signup-password">
          Password
          <input
            id="signup-password"
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
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
          disabled={submitting}
          className="w-full rounded bg-leovee-accent px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
        >
          {submitting ? "Creating…" : "Sign up"}
        </button>
        <p className="mt-4 text-center text-xs text-slate-500">
          Already have an account?{" "}
          <Link to="/login" className="text-leovee-accent hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </div>
  );
}
