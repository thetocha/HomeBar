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
        <header class="text-center">
          <p class="kicker">Service</p>
          <h1 class="mt-1 font-serif text-4xl italic">Djinn Antonic</h1>
          <p class="flourish my-4">✦</p>
        </header>
        <nav class="mb-6 grid grid-cols-3 overflow-hidden border border-gold">
          ${tabButton("orders", "Orders", tab)}
          ${tabButton("menu", "Menu", tab)}
          ${tabButton("new", editing ? "Edit drink" : "New drink", tab)}
        </nav>
        <section id="panel"></section>
      </main>
    `;
    root.querySelectorAll<HTMLButtonElement>("[data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        tab = btn.dataset.tab as Tab;
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
      tab = "menu";
      paint();
    });
  }

  paint();
}

function tabButton(id: Tab, label: string, current: Tab): string {
  const active = id === current ? "bg-ink text-cream" : "bg-[#fffaf0]/70 text-ink";
  return `<button type="button" data-tab="${id}" class="${active} px-2 py-2.5 text-xs uppercase tracking-[0.16em]">${label}</button>`;
}

async function renderMenu(panel: HTMLElement, onEdit: (drink: Cocktail) => void): Promise<void> {
  panel.innerHTML = `<p class="text-sm text-ink/55">Loading cards…</p>`;
  try {
    const drinks = await api.cocktails();
    if (!drinks.length) {
      panel.innerHTML = `<p class="text-sm text-ink/55">No cards yet. Add a drink.</p>`;
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
          toast(err instanceof Error ? err.message : "Could not update", "err");
        }
      });
    });
    panel.querySelectorAll<HTMLButtonElement>("[data-del]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("Take this card out of the book?")) return;
        try {
          await api.deleteCocktail(Number(btn.dataset.del));
          toast("Card removed");
          await renderMenu(panel, onEdit);
        } catch (err) {
          toast(err instanceof Error ? err.message : "Could not delete", "err");
        }
      });
    });
  } catch (err) {
    panel.innerHTML = `<p class="text-stamp">${escapeHtml(err instanceof Error ? err.message : "Error")}</p>`;
  }
}

function menuCard(drink: Cocktail): string {
  const photo = drink.photo_url
    ? photoImg(drink.photo_url, "", "h-20 w-20 object-cover")
    : `<div class="flex h-20 w-20 items-center justify-center bg-[#efe6d2] text-[10px] uppercase tracking-widest text-ink/40">No photo</div>`;
  return `
    <article class="ticket flex gap-3 p-3">
      <div class="polaroid !p-1 !pb-3">${photo}</div>
      <div class="min-w-0 flex-1">
        <div class="flex items-baseline justify-between gap-2">
          <h3 class="truncate font-serif text-xl italic">${escapeHtml(drink.name)}</h3>
          <span class="seal ${drink.available ? "seal-on" : "seal-out"}">${
            drink.available ? "On menu" : "Sold out"
          }</span>
        </div>
        <p class="mt-1 line-clamp-2 text-xs text-ink/60">${escapeHtml(drink.description || "")}</p>
        <div class="mt-3 flex flex-wrap gap-2">
          <button type="button" data-avail="${drink.id}" class="ghost-btn !px-2 !py-1 !text-[10px]">${
            drink.available ? "Mark sold out" : "Put back on"
          }</button>
          <button type="button" data-edit="${drink.id}" class="ghost-btn !px-2 !py-1 !text-[10px]">Edit</button>
          <button type="button" data-del="${drink.id}" class="ghost-btn !px-2 !py-1 !text-[10px]">Delete</button>
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
        panel.innerHTML = `<p class="text-sm text-ink/55">No tickets yet.</p>`;
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
            toast(err instanceof Error ? err.message : "Could not update order", "err");
          }
        });
      });
    } catch (err) {
      snapshot = "";
      panel.innerHTML = `<p class="text-stamp">${escapeHtml(err instanceof Error ? err.message : "Error")}</p>`;
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
  const handle = order.guest_username ? `@${order.guest_username}` : "no username";
  return `
    <article class="ticket px-3 py-3">
      <div class="flex items-start justify-between gap-3">
        <div>
          <p class="text-[10px] uppercase tracking-[0.18em] text-stamp">${STATUS_LABEL[order.status]} · #${order.id}</p>
          <h3 class="font-serif text-xl italic">${escapeHtml(order.cocktail_name)}</h3>
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
        <span class="text-xs uppercase tracking-[0.18em] text-gold">Name</span>
        <input name="name" required maxlength="120" class="field" value="${escapeHtml(drink?.name ?? "")}" />
      </label>
      <label class="block">
        <span class="text-xs uppercase tracking-[0.18em] text-gold">Description</span>
        <textarea name="description" rows="4" class="field">${escapeHtml(drink?.description ?? "")}</textarea>
      </label>
      <label class="flex items-center gap-2 text-sm">
        <input type="checkbox" name="available" ${drink?.available !== false ? "checked" : ""} />
        On the menu
      </label>
      <label class="block">
        <span class="text-xs uppercase tracking-[0.18em] text-gold">Polaroid</span>
        <input name="photo" type="file" accept="image/*" class="mt-2 block w-full text-sm" />
      </label>
      ${
        drink?.photo_url
          ? photoImg(drink.photo_url, "", "h-32 w-32 object-cover shadow-polaroid", false)
          : ""
      }
      <button type="submit" class="stamp-btn w-full">${isEdit ? "Save card" : "Add to the book"}</button>
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
    submit.textContent = "Saving…";
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
      toast(isEdit ? "Card updated" : "Drink added");
      onSaved();
    } catch (err) {
      haptic("error");
      toast(err instanceof Error ? err.message : "Could not save", "err");
      submit.disabled = false;
      submit.textContent = label;
    }
  });
}
