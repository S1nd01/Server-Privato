import { motion, useReducedMotion } from "motion/react";
import { VideoPlayer } from "./VideoPlayer.jsx";
import { Icon } from "./icons.jsx";
import { BADGES, BRAND, COPY, LOGOS, NAV, VIDEO_SRC } from "./config.js";

const glass = "border border-white/15 bg-white/[0.06] backdrop-blur-md";

export function Hero({ onEnter }) {
  const calm = useReducedMotion();   // chi ha chiesto meno movimento non vede ne' animazioni ne' video in riproduzione

  const container = { hidden: {}, show: { transition: { staggerChildren: calm ? 0 : 0.12, delayChildren: calm ? 0 : 0.15 } } };
  const item = {
    hidden: { opacity: 0, y: calm ? 0 : 24 },
    show: { opacity: 1, y: 0, transition: { duration: calm ? 0 : 0.7, ease: [0.22, 1, 0.36, 1] } },
  };

  return (
    <div className="relative flex min-h-[100dvh] flex-col overflow-hidden bg-black font-sans text-white">
      {/* Sfondo: 80vh, ancorato a 35vh dal basso, dietro al testo. Opacita' piena e nessun velo, come da progetto. */}
      <div className="absolute inset-x-0 bottom-[35vh] z-0 h-[80vh]">
        <VideoPlayer src={VIDEO_SRC} still={calm} className="h-full w-full object-cover" />
      </div>

      {/* Barra fissa, vetro sfocato */}
      <header className="fixed inset-x-0 top-0 z-50 border-b border-white/10 bg-black/30 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 pb-3 pt-[calc(env(safe-area-inset-top)+0.75rem)]">
          <span className="text-lg font-medium tracking-tight text-white">{BRAND}</span>

          {/* div con role, non <nav>/<main>: lo style.css del pannello stila quegli elementi in modo globale (barra a schede, padding) */}
          <div role="navigation" aria-label="Sezioni del pannello" className="hidden md:block">
            <ul className="flex items-center gap-1 text-sm">
              {NAV.map((n) => (
                <li key={n.label}>
                  {n.active ? (
                    // bordo sfumato: un involucro con sfondo a gradiente e 1px di padding
                    <span className="flex rounded-full bg-gradient-to-r from-white/70 via-white/10 to-white/60 p-px">
                      <button type="button" onClick={() => onEnter({ go: n.go })} className="flex items-center rounded-full bg-black/80 px-4 py-1.5 text-white">
                        {n.label}
                      </button>
                    </span>
                  ) : n.soon ? (
                    <span aria-disabled="true" title="In arrivo" className="flex cursor-not-allowed items-center px-4 py-1.5 text-white/40 line-through">{n.label}</span>
                  ) : (
                    <button type="button" onClick={() => onEnter({ go: n.go })} className="flex items-center rounded-full px-4 py-1.5 text-white/65 transition-colors hover:text-white">
                      {n.label}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>

          <button
            type="button"
            onClick={() => onEnter({})}
            className="rounded-full bg-gradient-to-b from-white to-neutral-400 px-5 py-2 text-sm font-medium text-black shadow-[0_0_24px_rgba(255,255,255,0.18)] transition hover:from-white hover:to-neutral-200"
          >
            {COPY.ctaNav}
          </button>
        </div>
      </header>

      {/* Contenuto centrato, sopra il video */}
      <div role="main" className="relative z-10 flex flex-1 flex-col items-center justify-center px-5 pb-10 pt-32 text-center">
        <motion.div variants={container} initial="hidden" animate="show" className="flex w-full max-w-4xl flex-col items-center">
          <motion.ul variants={item} className="mb-8 flex flex-wrap items-center justify-center gap-2.5" aria-label={COPY.badgeLead}>
            {BADGES.map((b) => (
              <li key={b.label} className={`inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-[13px] text-white/80 ${glass}`}>
                <span className="text-white/50">{COPY.badgeLead}</span>
                <Icon name={b.icon} size={15} className="text-white" />
                <span className="font-medium text-white">{b.label}</span>
              </li>
            ))}
          </motion.ul>

          <motion.h1 variants={item} className="text-balance text-[clamp(2.5rem,8.5vw,5rem)] font-medium leading-[1.02] tracking-tight text-white">
            {COPY.title}
          </motion.h1>

          <motion.p variants={item} className="mt-6 max-w-2xl text-balance text-base leading-relaxed text-white/70 sm:text-lg">
            {COPY.subtitle}
          </motion.p>

          <motion.div variants={item} className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <button
              type="button"
              onClick={() => onEnter({})}
              className="rounded-full border border-white bg-black px-7 py-3 text-[15px] font-medium text-white transition hover:bg-white hover:text-black"
            >
              {COPY.primary}
            </button>
            <button
              type="button"
              onClick={() => onEnter({ help: true })}
              className={`rounded-full px-7 py-3 text-[15px] font-medium text-white transition hover:bg-white/15 ${glass}`}
            >
              {COPY.secondary}
            </button>
          </motion.div>
        </motion.div>
      </div>

      {/* Fila di marchi segnaposto: statica, in scala di grigi al 40% */}
      <footer className="relative z-10 px-5 pb-8" aria-hidden="true">
        <ul className="mx-auto flex max-w-4xl flex-wrap items-center justify-center gap-x-10 gap-y-4 opacity-40 grayscale">
          {LOGOS.map((l) => (
            <li key={l.label} className="flex items-center gap-2 text-white">
              <Icon name={l.icon} size={22} />
              <span className="text-[15px] font-medium tracking-tight">{l.label}</span>
            </li>
          ))}
        </ul>
      </footer>
    </div>
  );
}
