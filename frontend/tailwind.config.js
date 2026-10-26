/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.ts"],
  theme: {
    extend: {
      colors: {
        cream: "#f4ead5",
        ink: "#1c1610",
        rule: "#c4a56a",
        stamp: "#6b2c1a",
        gold: "#b08d57",
      },
      fontFamily: {
        serif: ["Palatino Linotype", "Palatino", "Georgia", "serif"],
        sans: ["system-ui", "Segoe UI", "sans-serif"],
        script: ["Palatino Linotype", "Georgia", "cursive"],
      },
      boxShadow: {
        polaroid: "0 12px 22px rgba(40, 24, 8, 0.16)",
      },
    },
  },
  plugins: [],
};
