const apiBase = import.meta.env.VITE_API_URL ?? "";

export async function fetchHealth(): Promise<unknown> {
  const url = apiBase ? `${apiBase}/health/ready` : "/api/health/ready";
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }
  return response.json();
}
