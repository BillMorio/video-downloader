import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#070808",
        "bg-deep": "#030404",
        surface: "#131417",
        "surface-2": "#191a1e",
        border: "#26272b",
        brand: "#22c55e",
        "brand-hover": "#16a34a",
        "brand-soft": "#7dffa6",
        "on-brand": "#052e16",
      },
    },
  },
  plugins: [],
};
export default config;
