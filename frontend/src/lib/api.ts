const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEFAULT_TIMEOUT_MS = 120_000;

function fetchWithTimeout(url: string, options: RequestInit, ms = DEFAULT_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), ms);
  return fetch(url, { ...options, signal: controller.signal }).finally(() => clearTimeout(id));
}

export interface Source {
  key: string;
  name: string;
  icon: string;
  color: string;
  auth_type: string;
  description: string;
  available: boolean;
  coming_soon?: boolean;
  auto_connected?: boolean;
  category: string;
}

export type SourcesResponse = Record<string, Source[]>;

const API = {
  get: async (path: string) => {
    const res = await fetchWithTimeout(`${BASE_URL}${path}`, {});
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return { data };
  },
  post: async (path: string, body: unknown) => {
    const res = await fetchWithTimeout(`${BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`POST ${path} → ${res.status}`);
    const data = await res.json();
    return { data };
  },
  patch: async (path: string, body: unknown) => {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`PATCH ${path} → ${res.status}`);
    const data = await res.json();
    return { data };
  },
  delete: async (path: string) => {
    const res = await fetch(`${BASE_URL}${path}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`DELETE ${path} → ${res.status}`);
    return {};
  },
};

export default API;
