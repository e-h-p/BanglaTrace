export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const response = await fetch("/api" + path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  const data = await response.json().catch(() => null);
  if (!response.ok)
    throw new Error(
      data?.error?.message || `Request failed (${response.status}).`,
    );
  return data as T;
}
export function upload<T>(path: string, file: File) {
  const body = new FormData();
  body.append("file", file);
  return api<T>(path, { method: "POST", body });
}
export function location(s: {
  page_number: number | null;
  page_end: number | null;
  line_start: number | null;
  line_end: number | null;
  location_type: string;
}) {
  const page = s.page_number
    ? `Page ${s.page_number}${s.page_end !== s.page_number ? `–${s.page_end}` : ""} · `
    : "";
  return (
    page +
    (s.line_start
      ? `${s.location_type === "extracted" ? "Extracted l" : "L"}ines ${s.line_start}–${s.line_end}`
      : "Location unavailable")
  );
}
export const score = (v: number | null) => (v === null ? "—" : v.toFixed(3));
