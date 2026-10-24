export const API = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export const getKey = () => {
  try { return sessionStorage.getItem("adminKey") || ""; } catch { return ""; }
};
export const setKey = (k: string) => {
  try { sessionStorage.setItem("adminKey", k); } catch {}
};

export class ApiError extends Error {
  constructor(public status: number, public body: any) {
    super(body?.detail || `HTTP ${status}`);
  }
}

export async function api(path: string, init: RequestInit = {}) {
  const res = await fetch(API + path, {
    ...init,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getKey()}`, ...(init.headers || {}) },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body);
  return body;
}
