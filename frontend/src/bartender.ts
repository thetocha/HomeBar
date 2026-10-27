import { api } from "./api";
import { escapeHtml, formatTime, photoImg, toast } from "./dom";
import { preparePhoto } from "./image";
import { haptic } from "./telegram";
import type { Cocktail, Order } from "./types";
import { NEXT_LABEL, NEXT_STATUS, STATUS_LABEL } from "./types";

type Tab = "menu" | "orders" | "new";

let ordersTimer: number | null = null;

export function stopOrdersTimer(): void {
  if (ordersTimer != null) {
    window.clearInterval(ordersTimer);
    ordersTimer = null;
  }
}

export function renderBartender(root: HTMLElement): void {
  let tab: Tab = "orders";
  let editing: Cocktail | null = null;

  function paint(): void {
    stopOrdersTimer();
    root.innerHTML = `
      <main class="page-frame">
        <header class="jar-label mb-6 text-center">
          <p class="kicker">Смена</p>
          <h1 class="jar-title mt-2">Djinn Antonic</h1>
          <div class="smoke-line mx-auto mt-3"></div>
        </header>
        <nav class="mb-6 grid grid-cols-3 overflow-hidden border border-gold/80 bg-black/25">
          ${tabButton("orders", "Заказы", tab)}
          ${tabButton("menu", "Меню", tab)}
          ${tabButton("new", editing ? "Правка" : "Новый", tab)}
        </nav>
        <section id="panel"></section>
      </main>
    `;
    root.querySelectorAll<HTMLButtonElement>("[data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const next = btn.dataset.tab as Tab;
        if (next === tab) return;
        tab = next;
        if (tab !== "new") editing = null;
        paint();
      });
    });
    const panel = root.querySelector("#panel") as HTMLElement;
    if (tab === "menu") void renderMenu(panel, (drink) => {
      editing = drink;
      tab = "new";
      paint();
    });
    else if (tab === "orders") void renderOrders(panel);
    else renderForm(panel, editing, () => {
      editing = null;
      if (tab !== "new") return;
      tab = "menu";
      paint();
    });
  }

  paint();
}

function tabButton(id: Tab, label: string, current: Tab): string {
  const active = id === current ? "bg-stamp text-cream" : "bg-transparent text-cream/80";
  return `<button type="button" data-tab="${id}" class="${active} px-2 py-2.5 font-display text-[11px] uppercase tracking-[0.14em]">${label}</button>`;
}

async function renderMenu(panel: HTMLElement, onEdit: (drink: Cocktail) => void): Promise<void> {
  panel.innerHTML = `<p class="bar-muted font-serif text-lg italic">Загрузка карточек…</p>`;
  try {
    const drinks = await api.cocktails();
    if (!drinks.length) {
      panel.innerHTML = `<p class="bar-muted font-serif text-lg italic">Карточек пока нет. Добавьте напиток.</p>`;
      return;
    }
    panel.innerHTML = `<div class="space-y-4">${drinks.map(menuCard).join("")}</div>`;
    panel.querySelectorAll<HTMLButtonElement>("[data-edit]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const drink = drinks.find((item) => item.id === Number(btn.dataset.edit));
        if (drink) onEdit(drink);
      });
    });
    panel.querySelectorAll<HTMLButtonElement>("[data-avail]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = Number(btn.dataset.avail);
        const drink = drinks.find((item) => item.id === id);
        if (!drink) return;
        const form = new FormData();
        form.set("available", drink.available ? "false" : "true");
        try {
          await api.updateCocktail(id, form);
          haptic("light");
          await renderMenu(panel, onEdit);
        } catch (err) {
          toast(err instanceof Error ? err.message : "Не удалось обновить", "err");
        }
      });
    });
    panel.querySelectorAll<HTMLButtonElement>("[data-del]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("Убрать эту карточку из книги?")) return;
        try {
          await api.deleteCocktail(Number(btn.dataset.del));
          toast("Карточка убрана");
          await renderMenu(panel, onEdit);
        } catch (err) {
          toast(err instanceof Error ? err.message : "Не удалось удалить", "err");
        }
      });
    });
  } catch (err) {
    panel.innerHTML = `<p class="text-stamp">${escapeHtml(err instanceof Error ? err.message : "Ошибка")}</p>`;
  }
}

function menuCard(drink: Cocktail): string {
  const photo = drink.photo_url
    ? photoImg(drink.photo_url, "", "h-20 w-20 object-cover")
    : `<div class="flex h-20 w-20 items-center justify-center bg-[#efe4cc] font-serif text-sm italic text-ink/40">Нет фото</div>`;
  return `
    <article class="ticket flex gap-3 p-3">
      <div class="polaroid !p-1 !pb-3">${photo}</div>
      <div class="min-w-0 flex-1">
        <div class="flex items-baseline justify-between gap-2">
          <h3 class="truncate font-serif text-2xl italic leading-none">${escapeHtml(drink.name)}</h3>
          <span class="seal ${drink.available ? "seal-on" : "seal-out"}">${
            drink.available ? "В меню" : "Снят"
          }</span>
        </div>
        <p class="mt-1 line-clamp-2 text-xs text-ink/60">${escapeHtml(drink.description || "")}</p>
        <div class="mt-3 flex flex-wrap gap-2">
          <button type="button" data-avail="${drink.id}" class="ghost-btn !px-2 !py-1 !text-[10px]">${
            drink.available ? "Снять с меню" : "Вернуть"
          }</button>
          <button type="button" data-edit="${drink.id}" class="ghost-btn !px-2 !py-1 !text-[10px]">Изменить</button>
          <button type="button" data-del="${drink.id}" class="ghost-btn !px-2 !py-1 !text-[10px]">Удалить</button>
        </div>
      </div>
    </article>
  `;
}

async function renderOrders(panel: HTMLElement): Promise<void> {
  let snapshot = "";
  const draw = async (): Promise<void> => {
    try {
      const orders = await api.orders();
      const next = JSON.stringify(orders);
      if (next === snapshot) return;
      snapshot = next;
      if (!orders.length) {
        panel.innerHTML = `<p class="bar-muted font-serif text-lg italic">Заказов пока нет.</p>`;
        return;
      }
      panel.innerHTML = `<div class="space-y-3">${orders.map(orderCard).join("")}</div>`;
      panel.querySelectorAll<HTMLButtonElement>("[data-advance]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const id = Number(btn.dataset.advance);
          const next = btn.dataset.next as Order["status"];
          try {
            await api.setOrderStatus(id, next);
            haptic("success");
            await draw();
          } catch (err) {
            toast(err instanceof Error ? err.message : "Не удалось обновить заказ", "err");
          }
        });
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Ошибка";
      if (snapshot) {
        toast(message, "err");
      } else {
        panel.innerHTML = `<p class="text-stamp">${escapeHtml(message)}</p>`;
      }
    }
  };
  await draw();
  stopOrdersTimer();
  ordersTimer = window.setInterval(() => {
    void draw();
  }, 4000);
}

function orderCard(order: Order): string {
  const next = NEXT_STATUS[order.status];
  const action = next
    ? `<button type="button" data-advance="${order.id}" data-next="${next}" class="stamp-btn !px-3 !py-1 !text-[10px]">${NEXT_LABEL[order.status]}</button>`
    : "";
  const handle = order.guest_username ? `@${order.guest_username}` : "нет юзернейма";
  return `
    <article class="ticket px-3 py-3">
      <div class="flex items-start justify-between gap-3">
        <div>
          <p class="font-display text-[10px] uppercase tracking-[0.18em] text-stamp">${STATUS_LABEL[order.status]} · #${order.id}</p>
          <h3 class="font-serif text-2xl italic leading-none">${escapeHtml(order.cocktail_name)}</h3>
          <p class="text-sm">${escapeHtml(order.display_name)} <span class="text-ink/50">(${escapeHtml(handle)})</span></p>
          <p class="text-xs text-ink/50">${formatTime(order.created_at)}</p>
        </div>
        ${action}
      </div>
    </article>
  `;
}

function renderForm(panel: HTMLElement, drink: Cocktail | null, onSaved: () => void): void {
  const isEdit = Boolean(drink);
  panel.innerHTML = `
    <form id="drink-form" class="space-y-4">
      <label class="block">
        <span class="font-display text-xs uppercase tracking-[0.18em] text-gold">Название</span>
        <input name="name" required maxlength="120" class="field font-serif text-lg" value="${escapeHtml(drink?.name ?? "")}" />
      </label>
      <label class="block">
        <span class="font-display text-xs uppercase tracking-[0.18em] text-gold">Описание</span>
        <textarea name="description" rows="4" maxlength="4000" class="field font-serif text-lg">${escapeHtml(drink?.description ?? "")}</textarea>
      </label>
      <label class="flex items-center gap-2 font-serif text-lg">
        <input type="checkbox" name="available" ${drink?.available !== false ? "checked" : ""} />
        В меню
      </label>
      <label class="block">
        <span class="font-display text-xs uppercase tracking-[0.18em] text-gold">Полароид</span>
        <input name="photo" type="file" accept="image/*" class="mt-2 block w-full text-sm" />
      </label>
      ${
        drink?.photo_url
          ? `<div class="polaroid inline-block !p-1 !pb-3">${photoImg(drink.photo_url, "", "h-32 w-32 object-cover", false)}</div>`
          : ""
      }
      <button type="submit" class="stamp-btn w-full">${isEdit ? "Сохранить карточку" : "Добавить в меню"}</button>
    </form>
  `;

  const form = panel.querySelector("#drink-form") as HTMLFormElement;
  const photoInput = form.querySelector<HTMLInputElement>('[name="photo"]')!;
  let pendingPhoto: Promise<File | null> = Promise.resolve(null);
  photoInput.addEventListener("change", () => {
    const next = photoInput.files?.[0];
    pendingPhoto = next ? preparePhoto(next) : Promise.resolve(null);
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const available = form.querySelector<HTMLInputElement>('[name="available"]')?.checked ?? true;
    data.set("available", available ? "true" : "false");
    const file = photoInput.files?.[0];
    const submit = form.querySelector("button[type=submit]") as HTMLButtonElement;
    const label = submit.textContent;
    submit.disabled = true;
    submit.textContent = "Сохранение…";
    try {
      if (file) {
        const prepared = (await pendingPhoto) ?? (await preparePhoto(file));
        data.set("photo", prepared, prepared.name);
      } else {
        data.delete("photo");
      }
      if (drink) await api.updateCocktail(drink.id, data);
      else await api.createCocktail(data);
      haptic("success");
      toast(isEdit ? "Карточка обновлена" : "Напиток добавлен");
      onSaved();
    } catch (err) {
      haptic("error");
      toast(err instanceof Error ? err.message : "Не удалось сохранить", "err");
      submit.disabled = false;
      submit.textContent = label;
    }
  });
}
