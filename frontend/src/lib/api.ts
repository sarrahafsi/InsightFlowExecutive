const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Source {
  key: string;
  name: string;
  icon: string;
  color: string;
  auth_type: string;
  description: string;
  available: boolean;
  coming_soon?: boolean;
  category: string;
}

export type SourcesResponse = Record<string, Source[]>;

const API = {
  get: async (path: string) => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const res = await fetch(`${BASE_URL}${path}`, { signal: controller.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      return { data };
    } finally {
      clearTimeout(timeout);
    }
  },
  post: async (path: string, body: unknown) => {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`POST ${path} → ${res.status}`);
    const data = await res.json();
    return { data };
  },
};

export default API;
