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

function savedName(): string {
  return localStorage.getItem(NAME_KEY)?.trim() ?? "";
}

export function renderGuest(root: HTMLElement, me: Me): void {
  stopGuestTimer();
  if (!savedName()) {
    renderNamePrompt(root, me, () => renderGuest(root, me));
    return;
  }

  root.innerHTML = `
    <main class="page-frame">
      <header class="jar-label text-center">
        <h1 class="jar-title">Djinn Antonic</h1>
        <div class="smoke-line mx-auto my-3"></div>
        <p class="font-serif text-lg italic leading-snug text-ink/70">Закажите, что душа пожелает.</p>
      </header>
      <section id="catalog" class="mt-8 grid grid-cols-2 gap-5"></section>
      <section class="mt-10">
        <h2 class="bar-heading text-center">Ваши заказы</h2>
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
      renderCatalog(catalogEl, cocktails, sheetEl, (orders) => {
        ordersSnapshot = renderOrders(ordersEl, orders, "");
      });
      ordersSnapshot = renderOrders(ordersEl, orders, ordersSnapshot);
    } catch (err) {
      toast(err instanceof Error ? err.message : "Не удалось загрузить меню", "err");
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

function renderNamePrompt(root: HTMLElement, me: Me, onSaved: () => void): void {
  const preset = me.suggested_display_name.trim();
  root.innerHTML = `
    <main class="page-frame">
      <header class="jar-label text-center">
        <h1 class="jar-title">Djinn Antonic</h1>
        <div class="smoke-line mx-auto my-3"></div>
        <p class="font-serif text-lg italic text-ink/70">Как к вам обращаться?</p>
      </header>
      <label class="mt-8 block font-display text-xs uppercase tracking-[0.2em] text-gold" for="nickname">Имя на чеке</label>
      <input id="nickname" class="field font-serif text-lg" value="${escapeHtml(preset)}" maxlength="80" autocomplete="nickname" />
      <p class="bar-muted mt-3 text-center font-serif text-base italic">Один раз — и все следующие заказы пойдут на это имя.</p>
      <button id="save-name" type="button" class="stamp-btn mt-5 w-full">Продолжить</button>
    </main>
  `;

  const input = root.querySelector("#nickname") as HTMLInputElement;
  const save = async (): Promise<void> => {
    const name = input.value.trim();
    if (!name) {
      toast("Введите имя, чтобы бармен знал, для кого заказ", "err");
      input.focus();
      return;
    }
    localStorage.setItem(NAME_KEY, name);
    onSaved();
  };
  root.querySelector("#save-name")?.addEventListener("click", () => {
    void save();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") void save();
  });
}

function renderCatalog(
  catalogEl: HTMLElement,
  cocktails: Cocktail[],
  sheetEl: HTMLElement,
  onOrdered: (orders: Order[]) => void,
): void {
  if (!cocktails.length) {
    catalogEl.className = "mt-8";
    catalogEl.innerHTML = `<p class="bar-muted text-center font-serif text-lg italic">Бармен ещё составляет вечернее меню.</p>`;
    return;
  }
  catalogEl.innerHTML = cocktails
    .map((drink, index) => {
      const photo = drink.photo_url
        ? photoImg(drink.photo_url, drink.name, "aspect-square w-full object-cover")
        : `<div class="flex aspect-square items-center justify-center bg-[#efe4cc] font-serif text-xl italic text-ink/40">Нет фото</div>`;
      return `
        <button type="button" data-id="${drink.id}" class="rotate-card polaroid text-left ${index % 2 ? "mt-3" : ""}">
          ${photo}
          <figcaption class="mt-3 px-1 text-center font-serif text-xl italic leading-tight">${escapeHtml(drink.name)}</figcaption>
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
        openSheet(sheetEl, drink, onOrdered);
      }
    });
  });
}

function renderOrders(ordersEl: HTMLElement, orders: Order[], snapshot: string): string {
  const next = JSON.stringify(orders);
  if (next === snapshot) return snapshot;
  if (!orders.length) {
    ordersEl.innerHTML = `<p class="bar-muted font-serif text-lg italic">Пока ничего не заказано.</p>`;
    return next;
  }
  ordersEl.innerHTML = orders
    .map(
      (order) => `
        <article class="ticket px-3 py-3">
          <div class="flex items-baseline justify-between gap-3">
            <h3 class="font-serif text-xl italic">${escapeHtml(order.cocktail_name)}</h3>
            <span class="seal seal-out">${STATUS_LABEL[order.status]}</span>
          </div>
          <p class="mt-1 text-xs text-ink/55">${formatTime(order.created_at)} · для ${escapeHtml(order.display_name)}</p>
        </article>
      `,
    )
    .join("");
  return next;
}

function openSheet(
  sheetEl: HTMLElement,
  drink: Cocktail,
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
      <h2 class="mt-4 text-center font-serif text-4xl italic leading-none">${escapeHtml(drink.name)}</h2>
      <p class="mt-2 whitespace-pre-wrap text-center text-sm leading-relaxed text-ink/75">${escapeHtml(drink.description || "Без дегустационных заметок.")}</p>
      <button id="order-btn" type="button" class="stamp-btn mt-5 w-full">Заказать</button>
    </div>
  `;

  sheetEl.querySelector("[data-close]")?.addEventListener("click", () => {
    sheetEl.innerHTML = "";
  });

  sheetEl.querySelector("#order-btn")?.addEventListener("click", async () => {
    const name = savedName();
    if (!name) {
      toast("Сначала укажите имя", "err");
      return;
    }
    const button = sheetEl.querySelector("#order-btn") as HTMLButtonElement;
    button.disabled = true;
    try {
      await api.createOrder(drink.id, name);
      haptic("success");
      toast("Заказ принят. Бармен уже видит его.");
      sheetEl.innerHTML = "";
      onOrdered(await api.orders());
    } catch (err) {
      haptic("error");
      toast(err instanceof Error ? err.message : "Не удалось оформить заказ", "err");
      button.disabled = false;
    }
  });
}
