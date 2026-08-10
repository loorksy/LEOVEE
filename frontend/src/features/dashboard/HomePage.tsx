import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "@/api/health";

export function HomePage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  return (
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold">Welcome to Leovee</h1>
        <p className="mt-1 text-slate-400">
          AI market analyst workspace — project scaffolding is live.
        </p>
      </header>
      <section className="rounded-lg border border-slate-800 bg-leovee-panel p-6">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">API status</h2>
        {isLoading && <p className="mt-2 text-slate-400">Checking backend…</p>}
        {isError && (
          <p className="mt-2 text-amber-400">
            Backend unreachable. Start the API or use{" "}
            <code className="rounded bg-slate-800 px-1">docker compose up</code>.
          </p>
        )}
        {data !== undefined && (
          <pre className="mt-2 overflow-auto text-sm text-emerald-400">
            {JSON.stringify(data, null, 2)}
          </pre>
        )}
      </section>
    </div>
  );
}
