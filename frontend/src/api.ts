import { getInitData } from "./telegram";
import type { Cocktail, Me, Order, OrderStatus } from "./types";

const DEV_KEY = "homebar.devUserId";

export function getDevUserId(): number | null {
  const stored = sessionStorage.getItem(DEV_KEY);
  if (!stored) return null;
  const parsed = Number(stored);
  return Number.isFinite(parsed) ? parsed : null;
}

export function setDevUserId(id: number | null): void {
  if (id == null) sessionStorage.removeItem(DEV_KEY);
  else sessionStorage.setItem(DEV_KEY, String(id));
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const initData = getInitData();
  if (initData) headers.set("X-Telegram-Init-Data", initData);
  const devId = getDevUserId();
  if (!initData && devId != null) headers.set("X-Dev-Telegram-User-Id", String(devId));
  if (!headers.has("Accept")) headers.set("Accept", "application/json");

  const response = await fetch(path, { ...init, headers });
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  if (!response.ok) {
    let data: { detail?: unknown } | null = null;
    try {
      data = text ? (JSON.parse(text) as { detail?: unknown }) : null;
    } catch {
      data = null;
    }
    const detail = data?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((item: { msg?: string }) => item.msg).join(", ")
          : `Request failed (${response.status})`;
    throw new Error(message);
  }
  return (text ? JSON.parse(text) : null) as T;
}

export const api = {
  me: () => request<Me>("/api/me"),
  cocktails: () => request<Cocktail[]>("/api/cocktails"),
  cocktail: (id: number) => request<Cocktail>(`/api/cocktails/${id}`),
  createCocktail: (form: FormData) =>
    request<Cocktail>("/api/cocktails", { method: "POST", body: form }),
  updateCocktail: (id: number, form: FormData) =>
    request<Cocktail>(`/api/cocktails/${id}`, { method: "PATCH", body: form }),
  deleteCocktail: (id: number) =>
    request<void>(`/api/cocktails/${id}`, { method: "DELETE" }),
  orders: () => request<Order[]>("/api/orders"),
  createOrder: (cocktailId: number, displayName: string) =>
    request<Order>("/api/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cocktail_id: cocktailId, display_name: displayName }),
    }),
  setOrderStatus: (id: number, status: OrderStatus) =>
    request<Order>(`/api/orders/${id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }),
};
