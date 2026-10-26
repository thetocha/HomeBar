export function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function photoSrc(url: string | null): string {
  return url || "";
}

export function photoImg(url: string, alt: string, className: string, lazy = true): string {
  const loading = lazy ? "lazy" : "eager";
  return `<img src="${escapeHtml(photoSrc(url))}" alt="${escapeHtml(alt)}" class="${className}" loading="${loading}" decoding="async" />`;
}

export function toast(message: string, kind: "ok" | "err" = "ok"): void {
  document.getElementById("toast")?.remove();
  const el = document.createElement("div");
  el.id = "toast";
  el.className = `fixed left-1/2 top-6 z-[60] -translate-x-1/2 border px-4 py-2 text-sm shadow-polaroid ${
    kind === "ok" ? "border-gold bg-[#fffaf0] text-ink" : "border-stamp bg-white text-stamp"
  }`;
  el.textContent = message;
  document.body.appendChild(el);
  window.setTimeout(() => el.remove(), 2400);
}

export function formatTime(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
