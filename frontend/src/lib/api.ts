import { getToken } from "./auth";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEFAULT_TIMEOUT_MS = 120_000;

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

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
    const res = await fetchWithTimeout(`${BASE_URL}${path}`, {
      headers: { ...authHeaders() },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return { data };
  },
  post: async (path: string, body: unknown) => {
    const isFormData = body instanceof FormData;
    const res = await fetchWithTimeout(`${BASE_URL}${path}`, {
      method: "POST",
      headers: isFormData
        ? { ...authHeaders() }
        : { "Content-Type": "application/json", ...authHeaders() },
      body: isFormData ? body : JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`POST ${path} → ${res.status}`);
    const data = await res.json();
    return { data };
  },
  patch: async (path: string, body: unknown) => {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`PATCH ${path} → ${res.status}`);
    const data = await res.json();
    return { data };
  },
  delete: async (path: string) => {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: "DELETE",
      headers: { ...authHeaders() },
    });
    if (!res.ok) throw new Error(`DELETE ${path} → ${res.status}`);
    return {};
  },
};

export default API;
