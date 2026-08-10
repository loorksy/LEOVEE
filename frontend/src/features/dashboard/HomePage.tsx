import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "@/api/health";

function HealthErrorMessage() {
  if (import.meta.env.DEV) {
    return (
      <p className="mt-2 text-amber-400">
        Cannot reach the API. For local development, start the backend or run{" "}
        <code className="rounded bg-slate-800 px-1">docker compose up</code>.
      </p>
    );
  }
  return (
    <p className="mt-2 text-amber-400">
      We could not reach the Leovee service. Please try again in a few minutes. If the problem
      continues, contact support.
    </p>
  );
}

export function HomePage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  const healthy =
    data?.status === "ok" &&
    data.checks?.database?.ok !== false &&
    data.checks?.redis?.ok !== false;

  return (
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold">Welcome to Leovee</h1>
        <p className="mt-1 text-slate-400">AI market analyst workspace</p>
      </header>
      <section className="rounded-lg border border-slate-800 bg-leovee-panel p-6">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">API status</h2>
        {isLoading && <p className="mt-2 text-slate-400">Checking service…</p>}
        {isError && <HealthErrorMessage />}
        {data !== undefined && !isError && (
          <div className="mt-2">
            <p className={healthy ? "text-emerald-400" : "text-amber-400"}>
              {healthy ? "All systems operational" : "Service degraded — see details below"}
            </p>
            <pre className="mt-2 overflow-auto text-sm text-slate-400">
              {JSON.stringify(data, null, 2)}
            </pre>
          </div>
        )}
      </section>
    </div>
  );
}
