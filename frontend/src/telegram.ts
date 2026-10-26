declare global {
  interface Window {
    Telegram?: {
      WebApp: {
        initData: string;
        ready: () => void;
        expand: () => void;
        contentSafeAreaInset?: { top: number; bottom: number; left: number; right: number };
        safeAreaInset?: { top: number; bottom: number; left: number; right: number };
        HapticFeedback?: {
          impactOccurred: (style: "light" | "medium" | "heavy") => void;
          notificationOccurred: (type: "error" | "success" | "warning") => void;
        };
      };
    };
  }
}

export function bootTelegram(): void {
  const webApp = window.Telegram?.WebApp;
  if (!webApp) return;
  webApp.ready();
  webApp.expand();
  const inset = webApp.contentSafeAreaInset ?? webApp.safeAreaInset;
  if (inset) {
    const root = document.documentElement;
    root.style.setProperty("--safe-top", `${inset.top}px`);
    root.style.setProperty("--safe-bottom", `${inset.bottom}px`);
    root.style.setProperty("--safe-left", `${inset.left}px`);
    root.style.setProperty("--safe-right", `${inset.right}px`);
  }
}

export function getInitData(): string {
  return window.Telegram?.WebApp?.initData ?? "";
}

export function haptic(kind: "success" | "error" | "light" = "light"): void {
  const hapticApi = window.Telegram?.WebApp?.HapticFeedback;
  if (!hapticApi) return;
  if (kind === "success") hapticApi.notificationOccurred("success");
  else if (kind === "error") hapticApi.notificationOccurred("error");
  else hapticApi.impactOccurred("light");
}
