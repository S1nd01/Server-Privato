import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Nessun index.html: l'hero e' un modulo ES che il pannello carica con import("/hero/hero.js") (src/frontend/app.js).
// Modalita' libreria: conserva l'export mountHero e produce hero.js + hero.css (e hero-hls.js, caricato solo se serve).
// Nomi fissi, senza hash: nginx serve tutto con Cache-Control: no-cache, quindi il browser riconvalida sempre.
export default defineConfig({
  base: "/hero/",
  plugins: [react()],
  define: { "process.env.NODE_ENV": '"production"' },   // in modalita' libreria Vite non lo sostituisce, e React lo legge
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
    minify: true,
    chunkSizeWarningLimit: 700,   // hero-hls.js (hls.js) e' grande di suo, ma si scarica solo quando serve
    lib: { entry: "src/main.jsx", formats: ["es"], fileName: () => "hero.js", cssFileName: "hero" },
    rolldownOptions: { output: { chunkFileNames: "hero-[name].js", minify: true } },
  },
});
