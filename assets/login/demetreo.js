// Demetreo en el login (/login). Solo decoración: el formulario lo gestiona AuthState en Reflex.
//  - Los ojos siguen al puntero; al escribir el usuario siguen el texto.
//  - Contraseña enfocada: se tapa los ojos. Con «Mostrar»: baja una mano y espía con un ojo.
//  - Enviar con datos: rebote contento. Si llega un error (cambia el <p role="alert">): ¡ups!
//  - Clic en el aguacate: rebote. Con prefers-reduced-motion no hay rebotes ni temblores.
window.__avocadoOff?.();

const $ = (id) => document.getElementById(id);
const wrap = $("av-wrap");
const svg = $("av-svg");

if (wrap && svg) {
  const bounce = $("av-bounce"), mouth = $("av-mouth"), bubble = $("av-bubble");
  const bEmoji = $("av-bubble-emoji"), bText = $("av-bubble-text");
  const user = $("pl4-username"), pass = $("pl4-password"), ojo = $("pl4-ojo"), err = $("pl4-err");
  const form = pass?.closest("form");
  const pupils = [...svg.querySelectorAll(".pupil")];
  const browL = svg.querySelector(".eyebrow-left"), browR = svg.querySelector(".eyebrow-right");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const MOUTH = { idle: "M 168 173 Q 180 177 192 172", happy: "M 166 171 Q 180 184 194 171", oops: "M 168 178 Q 180 170 192 178" };
  let passFocus = false, passVisible = false, userFocus = false;
  let bubbleT = 0, mouthT = 0, raf = 0, px = 0, py = 0;
  const off = [];
  const on = (el, ev, fn, opts) => { el.addEventListener(ev, fn, opts); off.push(() => el.removeEventListener(ev, fn, opts)); };

  // Variante oculta (display: none) → no hay geometría: no se hace nada.
  const visible = () => svg.getClientRects().length > 0;

  const toSvg = (x, y) => {
    const ctm = svg.getScreenCTM();
    return ctm ? new DOMPoint(x, y).matrixTransform(ctm.inverse()) : { x: 180, y: 140 };
  };

  const lookAt = (tx, ty) => pupils.forEach((p) => {
    const cx = parseFloat(p.dataset.cx), cy = parseFloat(p.dataset.cy), max = parseFloat(p.dataset.max);
    const dx = tx - cx, dy = ty - cy, a = Math.atan2(dy, dx), d = Math.min(max, Math.hypot(dx, dy) * 0.055);
    p.style.transform = `translate(${(Math.cos(a) * d).toFixed(2)}px, ${(Math.sin(a) * d).toFixed(2)}px)`;
  });

  const say = (emoji, text, ms = 2600) => {
    bEmoji.textContent = emoji; bText.textContent = text;
    bubble.classList.add("is-on");
    clearTimeout(bubbleT);
    bubbleT = setTimeout(() => bubble.classList.remove("is-on"), ms);
  };

  const setMouth = (kind, ms = 1200) => {
    mouth.setAttribute("d", MOUTH[kind]);
    clearTimeout(mouthT);
    mouthT = setTimeout(() => mouth.setAttribute("d", MOUTH.idle), ms);
  };

  const play = (cls) => {
    if (reduce) return;
    bounce.classList.remove("avocado-happy", "avocado-oops");
    void bounce.getBoundingClientRect(); // reflow: reinicia la animación aunque se repita
    bounce.classList.add(cls);
  };

  const brows = (l = "", r = "") => { browL.style.transform = l; browR.style.transform = r; };

  const hands = () => {
    wrap.classList.remove("avocado-state-cover", "avocado-state-peek");
    if (!passFocus) return;
    if (passVisible) {
      wrap.classList.add("avocado-state-peek");
      const r = pass.getBoundingClientRect(), p = toSvg(r.left + 80, r.top + r.height / 2);
      lookAt(p.x, p.y);
    } else {
      wrap.classList.add("avocado-state-cover");
    }
  };

  // 1) Puntero (una actualización por fotograma)
  const aim = () => {
    raf = 0;
    // Reflex cambia de página sin recargar: si el login ya no está, se quitan los oyentes.
    if (!wrap.isConnected) { window.__avocadoOff?.(); return; }
    if (!visible() || userFocus || (passFocus && !passVisible)) return;
    const p = toSvg(px, py);
    lookAt(p.x, p.y);
  };
  on(window, "pointermove", (e) => { px = e.clientX; py = e.clientY; raf ||= requestAnimationFrame(aim); }, { passive: true });

  // 2) Usuario: los ojos siguen el final del texto
  const trackUser = () => {
    if (!visible()) return;
    const r = user.getBoundingClientRect(), pad = parseFloat(getComputedStyle(user).paddingLeft) || 16;
    const w = Math.min(r.width - 2 * pad, user.value.length * 8.6);
    const p = toSvg(r.left + pad + w, r.top + r.height / 2);
    lookAt(p.x, p.y);
    brows("translateY(-2px) rotate(-4deg)", "translateY(1px) rotate(3deg)");
  };
  on(user, "focus", () => { userFocus = true; passFocus = false; hands(); trackUser(); });
  on(user, "input", trackUser);
  on(user, "click", trackUser);
  on(user, "blur", () => { userFocus = false; brows(); });

  // 3) Contraseña: se tapa los ojos
  on(pass, "focus", () => {
    passFocus = true; userFocus = false; brows(); hands();
    if (!passVisible) say("🙈", "¡Tranquilo, no miro tu contraseña!", 2200);
  });
  on(pass, "blur", (e) => {
    if (e.relatedTarget === ojo) return; // pulsar «Mostrar» no debe bajar las manos
    passFocus = false; hands();
  });

  // 4) Mostrar / ocultar
  on(ojo, "mousedown", (e) => e.preventDefault()); // mantiene el foco en el campo
  on(ojo, "click", () => {
    passVisible = !passVisible;
    pass.type = passVisible ? "text" : "password";
    ojo.textContent = passVisible ? "Ocultar" : "Mostrar";
    ojo.setAttribute("aria-pressed", String(passVisible));
    pass.focus(); passFocus = true; hands();
    if (passVisible) say("🫣", "¡Solo un vistazo rápido con un ojo!", 2200);
    else say("🙈", "¡Ojos tapados de nuevo!", 1800);
  });

  // 5) Enviar y error
  if (form) on(form, "submit", () => {
    passFocus = false; userFocus = false; brows(); hands(); lookAt(180, 145);
    if (user.value.trim() && pass.value) { play("avocado-happy"); setMouth("happy"); say("🥑", "¡Entrando!", 1600); }
  });
  if (err) {
    const watcher = new MutationObserver(() => {
      const t = err.textContent.trim();
      if (!t) return;
      passFocus = false; hands(); play("avocado-oops"); setMouth("oops", 1800);
      brows("translateY(-3px) rotate(-10deg)", "translateY(-3px) rotate(10deg)");
      setTimeout(() => brows(), 1800);
      say("🤔", t, 3200);
    });
    watcher.observe(err, { childList: true, characterData: true, subtree: true });
    off.push(() => watcher.disconnect());
  }

  // 6) Clic en el aguacate
  on(wrap, "click", () => { play("avocado-happy"); setMouth("happy"); say("🥑", "¡Hola! Listo para entrar"); });

  window.__avocadoOff = () => { off.forEach((fn) => fn()); cancelAnimationFrame(raf); clearTimeout(bubbleT); clearTimeout(mouthT); };
}
