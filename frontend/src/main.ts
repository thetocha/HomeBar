import "./style.css";
import { api, setDevUserId } from "./api";
import { renderBartender, stopOrdersTimer } from "./bartender";
import { renderGuest, stopGuestTimer } from "./guest";
import { bootTelegram, getInitData } from "./telegram";
import type { Me } from "./types";

bootTelegram();

const GUEST_DEV_ID = 900000001;
const app = document.getElementById("app");
if (!app) throw new Error("#app missing");

void boot(app);

async function boot(root: HTMLElement): Promise<void> {
  root.innerHTML = `
    <main class="page-frame px-2 py-10 text-center">
      <header class="jar-label">
        <p class="kicker">Сегодня</p>
        <h1 class="jar-title mt-2">Djinn Antonic</h1>
        <div class="smoke-line mx-auto my-3"></div>
        <p class="font-serif text-lg italic text-ink/70">Открываем бар…</p>
      </header>
    </main>
  `;
  try {
    const me = await api.me();
    renderApp(root, me);
  } catch (err) {
    root.innerHTML = `
      <main class="page-frame px-2 py-10 text-center">
        <header class="jar-label">
          <h1 class="jar-title">Djinn Antonic</h1>
          <div class="smoke-line mx-auto my-3"></div>
          <p class="font-serif text-lg italic text-stamp">${err instanceof Error ? err.message : "Не удалось начать"}</p>
        </header>
        <p class="bar-muted mt-4 font-serif text-lg italic">Откройте это приложение из Telegram или задайте DEV_TELEGRAM_USER_ID для локального просмотра.</p>
      </main>
    `;
  }
}

function renderApp(root: HTMLElement, me: Me): void {
  const wrap = document.createElement("div");
  const stage = document.createElement("div");
  wrap.appendChild(stage);
  root.replaceChildren(wrap);

  if (me.dev_mode && !getInitData()) {
    wrap.prepend(devBar(me, async (id) => {
      setDevUserId(id);
      const next = await api.me();
      renderApp(root, next);
    }));
  }

  stopOrdersTimer();
  stopGuestTimer();
  if (me.is_bartender) renderBartender(stage);
  else renderGuest(stage, me);
}

function devBar(me: Me, onSwitch: (id: number) => void): HTMLElement {
  const bar = document.createElement("div");
  bar.className = "border-b border-gold/40 bg-[#140e0a]/80 px-3 py-2 text-center font-display text-[11px] uppercase tracking-[0.14em] text-cream";
  const bartenderId = me.bartender_telegram_id || 1;
  bar.innerHTML = `
    Локальный просмотр · сейчас вы <b>${me.is_bartender ? "бармен" : "гость"}</b>
    <span class="mx-2">·</span>
    <button type="button" data-as="bartender" class="underline">Бармен</button>
    <span class="mx-1">/</span>
    <button type="button" data-as="guest" class="underline">Гость</button>
  `;
  bar.querySelector("[data-as=bartender]")?.addEventListener("click", () => {
    onSwitch(bartenderId || 1);
  });
  bar.querySelector("[data-as=guest]")?.addEventListener("click", () => {
    onSwitch(GUEST_DEV_ID);
  });
  return bar;
}
