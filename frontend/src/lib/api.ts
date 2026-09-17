import { getToken } from "./auth";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEFAULT_TIMEOUT_MS = 120_000;

/**
 * Thrown on any non-2xx response. `body` is the parsed JSON error payload when available.
 * FastAPI wraps HTTPException(detail={...}) as {"detail": {...}} — for a plan-gated 403
 * this means `body.detail.feature` / `body.detail.current_plan`, NOT `body.feature`.
 */
export class ApiError extends Error {
  status: number;
  body: any;
  constructor(status: number, body: any) {
    super(`HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export function isUpgradeRequired(err: unknown): err is ApiError {
  return err instanceof ApiError && err.status === 403 && err.body?.detail?.detail === "upgrade_required";
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function fetchWithTimeout(url: string, options: RequestInit, ms = DEFAULT_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), ms);
  return fetch(url, { ...options, signal: controller.signal }).finally(() => clearTimeout(id));
}

async function parseBody(res: Response): Promise<any> {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

async function handle(res: Response): Promise<{ data: any }> {
  const data = await parseBody(res);
  if (!res.ok) throw new ApiError(res.status, data);
  return { data };
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
    return handle(res);
  },
  post: async (path: string, body: unknown, timeoutMs = DEFAULT_TIMEOUT_MS) => {
    const isFormData = body instanceof FormData;
    const res = await fetchWithTimeout(`${BASE_URL}${path}`, {
      method: "POST",
      headers: isFormData
        ? { ...authHeaders() }
        : { "Content-Type": "application/json", ...authHeaders() },
      body: isFormData ? body : JSON.stringify(body),
    }, timeoutMs);
    return handle(res);
  },
  patch: async (path: string, body: unknown) => {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
    });
    return handle(res);
  },
  delete: async (path: string) => {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: "DELETE",
      headers: { ...authHeaders() },
    });
    if (!res.ok) throw new ApiError(res.status, await parseBody(res));
    return {};
  },
};

export default API;
