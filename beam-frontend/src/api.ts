export async function api(path: string, data?: unknown) {
  const response = await fetch(path, {
    credentials: "same-origin",
    method: data === undefined ? "GET" : "POST",
    headers:
      data === undefined ? undefined : { "Content-Type": "application/json" },
    body: data === undefined ? undefined : JSON.stringify(data),
    signal: AbortSignal.timeout(12000),
  });
  const value = await response.json();
  if (response.status === 401)
    window.dispatchEvent(new Event("beam-auth-expired"));
  if (!response.ok)
    throw new Error(value.message || value.detail || `HTTP ${response.status}`);
  return value;
}
