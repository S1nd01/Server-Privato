/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{js,jsx}"],
  // Il pannello ha il suo style.css globale (h1, a, :focus-visible...): le utility dell'hero valgono solo dentro #hero-root
  // e con la specificita' di un id, cosi' non si pestano i piedi a vicenda.
  important: "#hero-root",
  corePlugins: { preflight: false },   // niente reset globale: lo fa src/hero.css, limitato a #hero-root
  theme: {
    extend: {
      fontFamily: { sans: ['"Bricolage Grotesque"', "system-ui", "sans-serif"] },   // il font gia' incluso nel pannello
    },
  },
};
