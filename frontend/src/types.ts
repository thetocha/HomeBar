export type OrderStatus = "pending" | "accepted" | "ready" | "done";

export interface Me {
  telegram_id: number;
  first_name: string;
  username: string | null;
  suggested_display_name: string;
  is_bartender: boolean;
  dev_mode: boolean;
  bartender_telegram_id: number | null;
}

export interface Cocktail {
  id: number;
  name: string;
  description: string;
  photo_url: string | null;
  available: boolean;
  created_at: string;
}

export interface Order {
  id: number;
  cocktail_id: number | null;
  cocktail_name: string;
  guest_telegram_id: number;
  guest_username: string | null;
  display_name: string;
  status: OrderStatus;
  created_at: string;
}

export const STATUS_LABEL: Record<OrderStatus, string> = {
  pending: "В очереди",
  accepted: "Готовится",
  ready: "Готов",
  done: "Подан",
};

export const NEXT_STATUS: Partial<Record<OrderStatus, OrderStatus>> = {
  pending: "accepted",
  accepted: "ready",
  ready: "done",
};

export const NEXT_LABEL: Partial<Record<OrderStatus, string>> = {
  pending: "Принять",
  accepted: "Готово",
  ready: "Подано",
};
