/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.ts"],
  theme: {
    extend: {
      colors: {
        cream: "#f4ead8",
        ink: "#24180f",
        rule: "#c4a35a",
        stamp: "#9c2436",
        gold: "#c4a35a",
        smoke: "#8fd4ea",
      },
      fontFamily: {
        serif: ["Cormorant Garamond", "Palatino Linotype", "Palatino", "Georgia", "serif"],
        sans: ["system-ui", "Segoe UI", "sans-serif"],
        display: ["Cinzel", "Palatino Linotype", "Palatino", "Georgia", "serif"],
      },
      boxShadow: {
        polaroid: "0 14px 28px rgba(0, 0, 0, 0.45)",
      },
    },
  },
  plugins: [],
};
