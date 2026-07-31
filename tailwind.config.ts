import type { Config } from "tailwindcss";

/**
 * Financial Times palette, Yahoo Finance layout.
 *
 * Flat by construction: no radius scale, no shadow scale, no gradients. If a
 * component wants elevation it has to reach outside the theme to get it, which
 * is the point — FT separates things with rules, not shadows.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        // Zero webfont bytes. FT's Financier/Metric are licensed, and the
        // nearest system stacks cost nothing and render on the first paint.
        serif: ['Georgia', '"Times New Roman"', 'Times', 'serif'],
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto',
               '"Helvetica Neue"', 'Arial', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      colors: {
        // FT surface family
        paper: "#FFF1E5",          // the signature warm background
        "paper-tint": "#F2E5DA",   // wells and hover states
        "paper-deep": "#E9DCD1",   // pressed / active
        ink: "#33302E",            // body copy
        "ink-strong": "#1A1817",   // headlines
        "ink-muted": "#66605C",    // bylines, timestamps
        rule: "#CCC1B7",           // section rules
        "rule-light": "#E6D9CE",   // list separators
        ftblue: "#0F5499",         // links
        claret: "#990F3D",         // FT accent
        teal: "#0D7680",
        // Both are checked against paper (#FFF1E5) *and* paper-tint (#F2E5DA),
        // at the 11px the ticker chips use: #00875A only reached 4.11:1 on
        // paper, so the green is darkened to clear 4.5:1 on the tint too.
        up: "#006B45",
        down: "#CC0000",

        // shadcn/radix primitives, remapped onto the FT palette so the dialog
        // inherits it instead of carrying the old dark theme around.
        border: "#CCC1B7",
        input: "#CCC1B7",
        ring: "#0F5499",
        background: "#FFF1E5",
        foreground: "#33302E",
        primary: { DEFAULT: "#0F5499", foreground: "#FFF1E5" },
        secondary: { DEFAULT: "#F2E5DA", foreground: "#33302E" },
        destructive: { DEFAULT: "#CC0000", foreground: "#FFF1E5" },
        muted: { DEFAULT: "#F2E5DA", foreground: "#66605C" },
        accent: { DEFAULT: "#F2E5DA", foreground: "#33302E" },
        popover: { DEFAULT: "#FFF1E5", foreground: "#33302E" },
        card: { DEFAULT: "#FFF1E5", foreground: "#33302E" },
      },
      borderRadius: {
        none: "0", sm: "0", DEFAULT: "0", md: "0", lg: "0", xl: "0", full: "9999px",
      },
      boxShadow: {
        none: "none", sm: "none", DEFAULT: "none", md: "none", lg: "none", xl: "none",
      },
      keyframes: {
        marquee: {
          from: { transform: "translateX(0)" },
          to: { transform: "translateX(-50%)" },
        },
      },
      animation: {
        marquee: "marquee var(--marquee-duration, 90s) linear infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
