import React, { useEffect, useRef } from "react";

export default function Welcome({ onEnter }) {
  const target = useRef(null);

  useEffect(() => {
    let active = true;
    let unmount;
    const element = target.current;
    const moduleUrl = new URL("/hero/hero.js", window.location.href).href;
    import(/* @vite-ignore */ moduleUrl)
      .then(async ({ mountHero }) => {
        if (!active) return;
        unmount = await mountHero(element, { onEnter });
        if (!active) unmount();
      })
      .catch(() => {
        if (active) onEnter();
      });

    return () => {
      active = false;
      if (unmount) queueMicrotask(unmount);
    };
  }, [onEnter]);

  return <div id="hero-root" ref={target} />;
}
