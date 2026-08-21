const TOKEN_KEY = "insightflow_token";
const USER_KEY  = "insightflow_user";

export interface AuthUser {
  id:         number;
  org_id:     string | null;
  email:      string;
  full_name:  string;
  role:       "superadmin" | "ceo" | "pm";
  is_active:  boolean;
  created_at: string;
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  // Also set cookie so Next.js middleware can read it
  document.cookie = `${TOKEN_KEY}=${token}; path=/; max-age=${8 * 3600}; SameSite=Lax`;
}

export function removeToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  document.cookie = `${TOKEN_KEY}=; path=/; max-age=0`;
}

export function getUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

export function setUser(user: AuthUser): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

export function logout(): void {
  removeToken();
  window.location.href = "/login";
}

export const ROLE_LABELS: Record<string, string> = {
  superadmin: "Super Admin",
  ceo:        "CEO",
  pm:         "Project Manager",
};

export const ROLE_COLORS: Record<string, string> = {
  superadmin: "#ef4444",
  ceo:        "#f59e0b",
  pm:         "#3b82f6",
};

// Helper guards (frontend)
export const isSuperAdmin = (user: AuthUser) => user.role === "superadmin";
export const isCEO        = (user: AuthUser) => user.role === "ceo" || user.role === "superadmin";
export const isPM         = (user: AuthUser) => user.role === "pm";
