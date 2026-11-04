/** Small fetch helpers shared by the key frames and shots screens. */

export async function detailOf(response: Response, fallback: string): Promise<string> {
  const body = (await response.clone().json().catch(() => ({}))) as { detail?: unknown };
  return typeof body.detail === "string" ? body.detail : fallback;
}

export async function postJson<T>(url: string, body?: Record<string, unknown>, fallback = "that didn't work"): Promise<T> {
  const res = await globalThis.fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) throw new Error(await detailOf(res, fallback));
  return (await res.json()) as T;
}

export async function postFile<T>(url: string, file: File, fallback = "could not upload that file"): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const res = await globalThis.fetch(url, { method: "POST", body: form });
  if (!res.ok) throw new Error(await detailOf(res, fallback));
  return (await res.json()) as T;
}
