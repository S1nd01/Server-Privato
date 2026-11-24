import { memo, useEffect, useRef } from "react";

const isHls = (src) => /\.m3u8(\?|$)/i.test(src);

/**
 * Video di sfondo: muto, in ciclo, senza controlli. Riproduce un flusso HLS (.m3u8) con hls.js, oppure direttamente
 * (Safari lo sa fare da solo, e un file .mp4 locale non ha bisogno di nulla). Memoizzato: si ricrea solo se cambia `src`.
 * Se il flusso non parte (offline, bloccato) il riquadro resta nero: l'hero non dipende dal video.
 */
function VideoPlayerBase({ src, className = "", still = false }) {
  const ref = useRef(null);

  useEffect(() => {
    const video = ref.current;
    if (!video || !src) return undefined;
    video.muted = true;   // React non imposta in modo affidabile l'attributo muted: senza, l'autoplay viene bloccato
    let hls = null;
    let cancelled = false;
    const play = () => { if (!still && !document.hidden) video.play().catch(() => { /* autoplay negato: resta il fotogramma */ }); };

    const native = !isHls(src) || video.canPlayType("application/vnd.apple.mpegurl");
    if (native) {
      video.src = src;
      play();
    } else {
      // hls.js pesa circa 500 KB: si scarica solo qui, e solo se il browser non legge gia' HLS
      import("hls.js").then(({ default: Hls }) => {
        if (cancelled || !Hls.isSupported()) return;
        hls = new Hls({
          enableWorker: false,          // il worker nascerebbe da un blob: la CSP (worker-src 'self') lo vieta
          capLevelToPlayerSize: true,   // non scarica una qualita' piu' alta di quella che si vede
          maxBufferLength: 20,
          maxMaxBufferLength: 40,
        });
        let retries = 0;
        hls.on(Hls.Events.ERROR, (_e, data) => {
          if (!data.fatal) return;
          if (data.type === Hls.ErrorTypes.NETWORK_ERROR && retries++ < 3) hls.startLoad();
          else if (data.type === Hls.ErrorTypes.MEDIA_ERROR && retries++ < 3) hls.recoverMediaError();
          else { hls.destroy(); hls = null; }   // si arrende: resta lo sfondo nero
        });
        hls.on(Hls.Events.MANIFEST_PARSED, play);
        hls.loadSource(src);
        hls.attachMedia(video);
      }).catch(() => { /* chunk non caricato: resta lo sfondo nero */ });
    }

    // in una scheda nascosta il video non deve consumare batteria
    const onVisibility = () => { if (document.hidden) video.pause(); else play(); };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibility);
      if (hls) hls.destroy();
      video.pause();
      video.removeAttribute("src");
      video.load();   // libera il decoder e la connessione
    };
  }, [src, still]);

  return (
    <video
      ref={ref}
      className={className}
      muted
      loop
      playsInline
      autoPlay={!still}
      preload="auto"
      tabIndex={-1}
      aria-hidden="true"
      disablePictureInPicture
    />
  );
}

export const VideoPlayer = memo(VideoPlayerBase);
