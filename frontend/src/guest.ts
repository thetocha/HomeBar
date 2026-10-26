import { api } from "./api";
import { escapeHtml, formatTime, photoImg, toast } from "./dom";
import { haptic } from "./telegram";
import type { Cocktail, Me, Order } from "./types";
import { STATUS_LABEL } from "./types";

const NAME_KEY = "homebar.displayName";

let ordersTimer: number | null = null;

export function stopGuestTimer(): void {
  if (ordersTimer != null) {
    window.clearInterval(ordersTimer);
    ordersTimer = null;
  }
}

export function renderGuest(root: HTMLElement, me: Me): void {
  stopGuestTimer();
  const storedName = localStorage.getItem(NAME_KEY);
  const displayName = storedName?.trim() || me.suggested_display_name;

  root.innerHTML = `
    <main class="page-frame">
      <header class="text-center">
        <p class="kicker">Tonight at the house</p>
        <h1 class="mt-1 font-serif text-[2.6rem] italic leading-none">Djinn Antonic</h1>
        <p class="flourish my-4">✦</p>
        <p class="text-sm italic text-ink/70">Order what you fancy.</p>
      </header>
      <section id="catalog" class="mt-8 grid grid-cols-2 gap-5"></section>
      <section class="mt-10">
        <h2 class="text-center font-serif text-2xl italic">Your orders</h2>
        <p class="flourish my-3">✦</p>
        <div id="orders" class="space-y-3"></div>
      </section>
    </main>
    <div id="sheet"></div>
  `;

  const catalogEl = root.querySelector("#catalog") as HTMLElement;
  const ordersEl = root.querySelector("#orders") as HTMLElement;
  const sheetEl = root.querySelector("#sheet") as HTMLElement;
  let ordersSnapshot = "";

  async function load(): Promise<void> {
    try {
      const [cocktails, orders] = await Promise.all([api.cocktails(), api.orders()]);
      renderCatalog(catalogEl, cocktails, displayName, sheetEl, (orders) => {
        ordersSnapshot = renderOrders(ordersEl, orders, "");
      });
      ordersSnapshot = renderOrders(ordersEl, orders, ordersSnapshot);
    } catch (err) {
      toast(err instanceof Error ? err.message : "Could not load menu", "err");
    }
  }

  void load();
  ordersTimer = window.setInterval(() => {
    void api
      .orders()
      .then((orders) => {
        ordersSnapshot = renderOrders(ordersEl, orders, ordersSnapshot);
      })
      .catch(() => undefined);
  }, 4000);
}

function renderCatalog(
  catalogEl: HTMLElement,
  cocktails: Cocktail[],
  displayName: string,
  sheetEl: HTMLElement,
  onOrdered: (orders: Order[]) => void,
): void {
  if (!cocktails.length) {
    catalogEl.className = "mt-8";
    catalogEl.innerHTML = `<p class="text-center text-ink/60">The bartender is still writing tonight’s menu.</p>`;
    return;
  }
  catalogEl.innerHTML = cocktails
    .map((drink, index) => {
      const photo = drink.photo_url
        ? photoImg(drink.photo_url, drink.name, "aspect-square w-full object-cover")
        : `<div class="flex aspect-square items-center justify-center bg-[#efe6d2] font-serif text-ink/40">No photo</div>`;
      return `
        <button type="button" data-id="${drink.id}" class="rotate-card polaroid text-left ${index % 2 ? "mt-3" : ""}">
          ${photo}
          <figcaption class="mt-3 px-1 text-center font-serif text-lg leading-tight">${escapeHtml(drink.name)}</figcaption>
          <p class="mt-1 line-clamp-2 px-1 text-center text-xs text-ink/60">${escapeHtml(drink.description || "")}</p>
        </button>
      `;
    })
    .join("");

  catalogEl.querySelectorAll<HTMLButtonElement>("button[data-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = Number(btn.dataset.id);
      const drink = cocktails.find((item) => item.id === id);
      if (drink) {
        openSheet(sheetEl, drink, displayName, onOrdered);
      }
    });
  });
}

function renderOrders(ordersEl: HTMLElement, orders: Order[], snapshot: string): string {
  const next = JSON.stringify(orders);
  if (next === snapshot) return snapshot;
  if (!orders.length) {
    ordersEl.innerHTML = `<p class="text-sm text-ink/55">Nothing ordered yet.</p>`;
    return next;
  }
  ordersEl.innerHTML = orders
    .map(
      (order) => `
        <article class="ticket px-3 py-3">
          <div class="flex items-baseline justify-between gap-3">
            <h3 class="font-serif text-lg italic">${escapeHtml(order.cocktail_name)}</h3>
            <span class="seal seal-out">${STATUS_LABEL[order.status]}</span>
          </div>
          <p class="mt-1 text-xs text-ink/55">${formatTime(order.created_at)} · for ${escapeHtml(order.display_name)}</p>
        </article>
      `,
    )
    .join("");
  return next;
}

function openSheet(
  sheetEl: HTMLElement,
  drink: Cocktail,
  initialName: string,
  onOrdered: (orders: Order[]) => void,
): void {
  const photo = drink.photo_url
    ? photoImg(drink.photo_url, drink.name, "max-h-64 w-full object-cover", false)
    : "";
  sheetEl.innerHTML = `
    <div class="sheet-backdrop" data-close="1"></div>
    <div class="sheet-panel">
      <div class="mx-auto mb-3 h-1 w-12 rounded-full bg-rule"></div>
      ${photo ? `<div class="polaroid mx-auto max-w-xs">${photo}</div>` : ""}
      <h2 class="mt-4 text-center font-serif text-3xl italic">${escapeHtml(drink.name)}</h2>
      <p class="mt-2 whitespace-pre-wrap text-center text-sm leading-relaxed text-ink/75">${escapeHtml(drink.description || "No tasting notes.")}</p>
      <label class="mt-5 block text-xs uppercase tracking-[0.2em] text-gold">Your name on the ticket</label>
      <input id="display-name" class="field" value="${escapeHtml(initialName)}" maxlength="80" />
      <button id="order-btn" type="button" class="stamp-btn mt-4 w-full">Order</button>
    </div>
  `;

  sheetEl.querySelector("[data-close]")?.addEventListener("click", () => {
    sheetEl.innerHTML = "";
  });

  sheetEl.querySelector("#order-btn")?.addEventListener("click", async () => {
    const input = sheetEl.querySelector("#display-name") as HTMLInputElement;
    const name = input.value.trim();
    if (!name) {
      toast("Add a name so the bartender knows who it's for", "err");
      return;
    }
    const button = sheetEl.querySelector("#order-btn") as HTMLButtonElement;
    button.disabled = true;
    try {
      localStorage.setItem(NAME_KEY, name);
      await api.createOrder(drink.id, name);
      haptic("success");
      toast("Ticket in. The bartender has it.");
      sheetEl.innerHTML = "";
      onOrdered(await api.orders());
    } catch (err) {
      haptic("error");
      toast(err instanceof Error ? err.message : "Could not order", "err");
      button.disabled = false;
    }
  });
}
