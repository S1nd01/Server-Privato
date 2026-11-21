import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./hero.css";   // in modalita' libreria finisce in dist/hero.css, accanto a hero.js
import { Hero } from "./Hero.jsx";

/**
 * Monta l'hero dentro `el` (il div #hero-root della pagina) e restituisce la funzione che lo smonta.
 * Il foglio di stile si carica con un <link> (la CSP del pannello vieta gli <style> iniettati) e si aspetta che sia pronto,
 * cosi' la schermata non compare mai senza stile.
 */
export async function mountHero(el, { onEnter }) {
  const link = document.createElement("link");
  link.rel = "stylesheet";
  // Percorso relativo a questo modulo (/hero/hero.js -> /hero/hero.css). `here` evita che Vite scambi new URL(..., import.meta.url)
  // per un asset da incorporare: ne uscirebbe un data: URI col CSS non compilato, che la CSP del pannello blocca.
  const here = import.meta.url;
  link.href = new URL("hero.css", here).href;
  await new Promise((resolve, reject) => {
    link.onload = resolve;
    link.onerror = () => reject(new Error("stile dell'hero non caricato"));
    document.head.appendChild(link);
  }).catch((e) => { link.remove(); throw e; });

  const root = createRoot(el);
  root.render(<StrictMode><Hero onEnter={onEnter} /></StrictMode>);
  return () => { root.unmount(); link.remove(); };
}
