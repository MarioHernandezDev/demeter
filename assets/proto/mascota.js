// Demeter · Demetreo, la mascota (aguacate vestido de griego).
// Sale solo en tres sitios: el pie de página, la página 404 y el aviso cuando entra una alerta nueva.
// Estados (data-mood): "ok" (adormilado), "alerta" (ojos abiertos, sudando) y "perdido" (404, mira a todos lados).
// Los ojos siguen al puntero en el navegador; el estado de ánimo sale de los datos (avisos sin leer).
(() => {
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
let uid = 0;

/* ---------------------------------------------------------------- el dibujo */
// Demetreo vestido de griego: corona de olivo, quitón blanco con greca dorada, fíbula, cetro dorado y sandalias.
// pose: "foot" (pie de página: asoma la cabeza con la corona), "senal" (aviso: apunta al bocadillo con el cetro y saluda),
// "mapa" (404: cuerpo entero con el mapa al revés y el cetro).
const VB = { foot: "0 0 200 262", senal: "-112 0 332 262", mapa: "-34 0 292 316" };
const GOLD = "#e2b23c", GOLD_D = "#a7741b";
function aguacate(mood = "ok", extra = "", pose = "foot") {
  const id = `ag${++uid}`;
  const eye = (cx, side) => `
    <g class="ag__eye">
      <clipPath id="${id}c${side}"><ellipse cx="${cx}" cy="111" rx="17" ry="15.6"/></clipPath>
      <ellipse cx="${cx}" cy="112" rx="15" ry="14" fill="url(#${id}w)"/>
      <g class="ag__pupil" data-cx="${cx}" data-cy="112"><circle cx="${cx}" cy="113" r="7.5" fill="#1f2618"/><circle cx="${cx + 2.8}" cy="110" r="2.4" fill="#fff"/><circle cx="${cx - 2.4}" cy="116" r="1" fill="#fff" opacity=".7"/></g>
      <g clip-path="url(#${id}c${side})"><g class="ag__lidg">
        <path d="M${cx - 19} 70H${cx + 19}V126Q${cx} 133 ${cx - 19} 126Z" fill="url(#${id}l)"/>
        <path d="M${cx - 18} 126Q${cx} 133 ${cx + 18} 126" fill="none" stroke="#4d6a24" stroke-width="2.2" stroke-linecap="round"/>
      </g></g>
    </g>`;
  const SKIN = "M100 6C132 6 148 40 158 78c12 42 36 70 36 108 0 46-42 72-94 72S6 232 6 186c0-38 24-66 36-108C52 40 68 6 100 6Z";
  const hand = (x, y) => `<circle cx="${x}" cy="${y}" r="8.5" fill="#3e5a22" stroke="#2c4317" stroke-width="2.5"/>`;
  const arm = (d) => `<path d="${d}" fill="none" stroke="#2c4317" stroke-width="6" stroke-linecap="round"/>`;

  // ---- corona de olivo: dos ramas que suben por la frente, hojas a los dos lados y aceitunas
  const branch = (s) => {
    const P = (t) => { const x0 = 100 - s * 52, y0 = 80, cx = 100 - s * 44, cy = 34, x1 = 100 - s * 8, y1 = 26;
      return [(1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x1, (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y1,
              2 * (1 - t) * (cx - x0) + 2 * t * (x1 - cx), 2 * (1 - t) * (cy - y0) + 2 * t * (y1 - cy)]; };
    let g = `<path d="M${100 - s * 52} 80Q${100 - s * 44} 34 ${100 - s * 8} 26" fill="none" stroke="#4d6a24" stroke-width="2.6" stroke-linecap="round"/>`;
    [0.12, 0.3, 0.48, 0.66, 0.84, 0.98].forEach((t, k) => {
      const [x, y, dx, dy] = P(t), a = Math.atan2(dy, dx) * 180 / Math.PI;
      [-1, 1].forEach((side) => {
        if (k === 5 && side < 0) return;
        const r = (a + 90 + side * 52) * Math.PI / 180, lx = x + Math.cos(r - Math.PI / 2) * 7, ly = y + Math.sin(r - Math.PI / 2) * 7;
        g += `<ellipse cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" rx="3.6" ry="8.2" transform="rotate(${(a + 90 + side * 52 - 90).toFixed(0)} ${lx.toFixed(1)} ${ly.toFixed(1)})" fill="#8bab4a" stroke="#4d6a24" stroke-width="1.4"/>`;
      });
    });
    [0.22, 0.58].forEach((t) => { const [x, y] = P(t); g += `<ellipse cx="${(x + s * 5).toFixed(1)}" cy="${(y + 5).toFixed(1)}" rx="4.6" ry="5.4" fill="#3d3048"/><circle cx="${(x + s * 5 - 1.6).toFixed(1)}" cy="${(y + 3).toFixed(1)}" r="1.3" fill="#8d7fa0"/>`; });
    return g;
  };
  const wreath = `<g class="ag__wreath">${branch(1)}${branch(-1)}</g>`;

  // ---- quitón: tela blanca en diagonal (del costado al hombro derecho), ribete con greca, fíbula y cinturón
  const A = [-6, 262], B = [158, 104], n = [8.3, 8.7]; // la diagonal deja ver el hueso, como en el dibujo
  const band = `${A[0]},${A[1]} ${B[0]},${B[1]} ${B[0] + n[0]},${B[1] + n[1]} ${A[0] + n[0]},${A[1] + n[1]}`;
  const cloth = `${A[0] + n[0]},${A[1] + n[1]} ${B[0] + n[0]},${B[1] + n[1]} 214,118 214,272 -12,272 -12,224`;
  const toga = `
    <g clip-path="url(#${id}k)">
      <polygon points="${cloth}" fill="#fbfaf4"/>
      <path d="M70 232 C100 214 130 190 160 140 M90 250 C130 230 160 200 190 160 M130 256 C160 240 180 220 196 196" fill="none" stroke="#dfe3da" stroke-width="2.5" stroke-linecap="round"/>
      <polygon points="${band}" fill="url(#${id}g)" stroke="${GOLD_D}" stroke-width="1.5"/>
      <polygon points="52,214 214,214 214,223 43,223" fill="${GOLD}" stroke="${GOLD_D}" stroke-width="1.5"/>
    </g>
    <circle cx="157" cy="103" r="9" fill="${GOLD}" stroke="${GOLD_D}" stroke-width="2"/><circle cx="154" cy="100" r="2.6" fill="#f7dc8c"/>`;
  // falda por debajo del aguacate, con la greca en el bajo
  const skirt = pose === "foot" ? "" : `
    <path d="M18 222H182L192 268H8Z" fill="#fbfaf4" stroke="#c9cfc6" stroke-width="2" stroke-linejoin="round"/>
    <path d="M60 224 54 266M100 224V266M140 224 146 266" stroke="#dfe3da" stroke-width="2.5"/>
    <rect x="8" y="252" width="184" height="14" fill="url(#${id}m)" stroke="${GOLD_D}" stroke-width="1.5"/>`;

  // ---- cetro dorado (vertical en la 404; en el aviso, inclinado apuntando al bocadillo)
  const scepter = (x1, y1, x2, y2) => {
    const a = Math.atan2(y2 - y1, x2 - x1) * 180 / Math.PI + 90; // gira la punta hacia donde apunta el cetro
    return `<g class="ag__scepter">
      <line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${GOLD_D}" stroke-width="10" stroke-linecap="round"/>
      <line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${GOLD}" stroke-width="6" stroke-linecap="round"/>
      <g transform="translate(${x2} ${y2}) rotate(${a.toFixed(0)})">
        <path d="M-11 4 Q-12 -10 0 -14 Q12 -10 11 4 Z" fill="${GOLD}" stroke="${GOLD_D}" stroke-width="2"/>
        <path d="M-6 -2 V-9 M0 -2 V-12 M6 -2 V-9" stroke="${GOLD_D}" stroke-width="1.6" stroke-linecap="round"/>
        <rect x="-9" y="3" width="18" height="5" rx="2" fill="${GOLD}" stroke="${GOLD_D}" stroke-width="1.6"/>
        <circle cy="-20" r="6" fill="${GOLD}" stroke="${GOLD_D}" stroke-width="2"/><circle cx="-2" cy="-22" r="1.8" fill="#fbe7a6"/>
      </g></g>`;
  };

  // ---- detrás del cuerpo
  let back = "", front = "";
  if (pose === "senal") {
    back = `<g class="ag__wave">${arm("M160 150Q194 136 202 102")}${hand(203, 97)}</g>`;
    front = `<g class="ag__arm-l">${arm("M40 156Q12 152-8 127")}${scepter(22, 152, -84, 58)}
      <g class="ag__spark" stroke="${GOLD}" stroke-width="3" stroke-linecap="round"><path d="M-104 30l-6-6M-110 50h-9M-90 22v-9"/></g>${hand(-8, 127)}</g>`;
  } else if (pose === "mapa") {
    const leg = (x, cls) => `<g class="ag__leg ${cls}">${arm(`M${x} 262L${x} 296`)}
      <path d="M${x - 6} 274l12 8M${x + 6} 274l-12 8M${x - 6} 284l12 8" stroke="#8a5a33" stroke-width="2.5" stroke-linecap="round"/>
      <ellipse cx="${x}" cy="302" rx="15" ry="5" fill="#8a5a33" stroke="#5e3b1f" stroke-width="2"/><ellipse cx="${x}" cy="298" rx="11" ry="6" fill="#3e5a22" stroke="#2c4317" stroke-width="2.5"/>
      <path d="M${x - 10} 298h20" stroke="#8a5a33" stroke-width="3"/></g>`;
    back = leg(82, "ag__leg--l") + leg(118, "ag__leg--r");
    front = `
    ${arm("M176 166Q208 176 226 192")}${scepter(226, 300, 226, 96)}${hand(226, 192)}
    ${arm("M26 168Q12 214 46 224")}
    <g class="ag__map" transform="rotate(-7 70 226)">
      <path d="M22 198l6 3 7-3 8 2 9-2 7 3 9-2 8 2 9-2 9 3 10-2-2 9 3 9-3 10 2 9-3 9 2 8-9-2-8 3-9-2-10 2-8-3-9 2-9-2-8 3-9-2-6 2 2-9-3-9 3-9-2-9 3-9z" fill="#ead9b0" stroke="#b49a6a" stroke-width="2" stroke-linejoin="round"/>
      <path d="M54 200v50M86 199v50" stroke="#d4c094" stroke-width="2"/>
      <rect x="30" y="206" width="18" height="13" rx="2" fill="#b9d06c"/><rect x="60" y="226" width="20" height="14" rx="2" fill="#b9d06c"/><rect x="92" y="206" width="16" height="12" rx="2" fill="#cfdf94"/>
      <path d="M36 232l7 7M43 232l-7 7" stroke="#c4472a" stroke-width="2.5" stroke-linecap="round"/>
      <path d="M64 212q10 6 24 2" fill="none" stroke="#8fa3b5" stroke-width="2" stroke-dasharray="3 3"/>
      <g transform="rotate(180 100 236)"><path d="M100 228l4 10h-8Z" fill="#c4472a"/><text x="100" y="248" text-anchor="middle" font-family="Mona Sans, sans-serif" font-weight="800" font-size="9" fill="#5a4a2a">N</text></g>
    </g>
    ${hand(46, 224)}`;
  }
  const pat = `
      <pattern id="${id}m" width="14" height="14" patternUnits="userSpaceOnUse"><rect width="14" height="14" fill="${GOLD}"/><path d="M0 11H10V3H4V8H7" fill="none" stroke="${GOLD_D}" stroke-width="1.6"/></pattern>
      <pattern id="${id}g" width="12" height="12" patternUnits="userSpaceOnUse" patternTransform="rotate(-44)"><rect width="12" height="12" fill="${GOLD}"/><path d="M0 9.5H8.5V2.5H3.5V7H6" fill="none" stroke="${GOLD_D}" stroke-width="1.4"/></pattern>`;
  return `<svg class="ag ag--${pose} ${extra}" data-mood="${mood}" viewBox="${VB[pose]}" aria-hidden="true" focusable="false">
    <defs>
      <radialGradient id="${id}f" cx="50%" cy="58%" r="60%"><stop offset="0" stop-color="#e9f1b9"/><stop offset=".7" stop-color="#d6e59a"/><stop offset="1" stop-color="#c3d77c"/></radialGradient>
      <linearGradient id="${id}s" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4b6a2a"/><stop offset="1" stop-color="#2f4a19"/></linearGradient>
      <radialGradient id="${id}h" cx="38%" cy="34%" r="70%"><stop offset="0" stop-color="#a5744a"/><stop offset=".55" stop-color="#8a5a33"/><stop offset="1" stop-color="#6e4325"/></radialGradient>
      <radialGradient id="${id}w" cx="45%" cy="35%" r="75%"><stop offset=".6" stop-color="#fff"/><stop offset="1" stop-color="#e3ead6"/></radialGradient>
      <linearGradient id="${id}l" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#a6c665"/><stop offset="1" stop-color="#86a847"/></linearGradient>
      <clipPath id="${id}k"><path d="${SKIN}"/></clipPath>${pat}
    </defs>
    ${back}${skirt}
    <path d="${SKIN}" fill="url(#${id}s)" stroke="#2c4317" stroke-width="5"/>
    <path d="${SKIN}" fill="none" stroke="#587a33" stroke-width="2.2" stroke-dasharray="0.1 8" opacity=".8" stroke-linecap="round" transform="translate(100 140) scale(.985) translate(-100 -140)"/>
    <path d="M100 22c24 0 36 28 45 62 11 40 33 64 33 102 0 36-36 57-78 57S22 222 22 186c0-38 22-62 33-102 9-34 21-62 45-62Z" fill="url(#${id}f)" stroke="#b9d06c" stroke-width="7"/>
    <circle cx="100" cy="186" r="43" fill="url(#${id}h)"/>
    <ellipse cx="85" cy="168" rx="11" ry="6.5" fill="#c08d5f" opacity=".55" transform="rotate(-28 85 168)"/>
    ${toga}
    <ellipse class="ag__cheek" cx="56" cy="134" rx="9" ry="5.5" fill="#ee9f80" opacity=".38"/><ellipse class="ag__cheek" cx="144" cy="134" rx="9" ry="5.5" fill="#ee9f80" opacity=".38"/>
    ${eye(76, "l")}${eye(124, "r")}
    <path class="ag__brow ag__brow--l" d="M60 90 L88 84" stroke="#2c4317" stroke-width="4" stroke-linecap="round"/>
    <path class="ag__brow ag__brow--r" d="M112 84 L140 90" stroke="#2c4317" stroke-width="4" stroke-linecap="round"/>
    <path class="ag__mouth ag__mouth--ok" d="M93 138 Q100 143 107 138" fill="none" stroke="#2c4317" stroke-width="3" stroke-linecap="round"/>
    <ellipse class="ag__mouth ag__mouth--alerta" cx="100" cy="140" rx="4.5" ry="5.5" fill="#2c4317"/>
    <path class="ag__mouth ag__mouth--perdido" d="M92 141 L108 138" fill="none" stroke="#2c4317" stroke-width="3" stroke-linecap="round"/>
    ${wreath}
    <path class="ag__drop" d="M164 70c0 0-9 11-9 17a9 9 0 0 0 18 0c0-6-9-17-9-17Z" fill="#8cc4ee" stroke="#4f8fc0" stroke-width="2"/>
    <text class="ag__q" x="168" y="56" font-family="Mona Sans, sans-serif" font-weight="800" font-size="40" fill="#3e5a22">?</text>
    ${front}
  </svg>`;
}

/* ---------------------------------------------------------------- ojos que siguen al puntero */
// Una sola escucha para todas las mascotas; solo se mueven las que están en pantalla.
const live = new Set();
const io = "IntersectionObserver" in window ? new IntersectionObserver((es) => es.forEach((e) => e.target._vis = e.isIntersecting)) : null;
function track(svg) { svg._vis = !io; io && io.observe(svg); live.add(svg); svg.style.setProperty("--lid", lidFor(svg)); }
let px = innerWidth / 2, py = innerHeight / 2, raf = 0;
function aim() {
  raf = 0;
  live.forEach((svg) => {
    if (!svg._vis || svg.dataset.mood === "perdido") return;
    const r = svg.getBoundingClientRect(), vb = svg.viewBox.baseVal, k = vb.width / r.width;
    $$(".ag__pupil", svg).forEach((p) => {
      const ex = r.left + (p.dataset.cx - vb.x) / k, ey = r.top + (p.dataset.cy - vb.y) / k;
      const dx = px - ex, dy = py - ey, a = Math.atan2(dy, dx), d = Math.min(5.5, Math.hypot(dx, dy) / 40);
      p.style.transform = `translate(${(Math.cos(a) * d).toFixed(2)}px, ${(Math.sin(a) * d * .8).toFixed(2)}px)`;
    });
    // si te acercas, se despierta un poco (solo en "ok")
    const near = Math.hypot(px - (r.left + (100 - vb.x) / k), py - (r.top + (112 - vb.y) / k)) < 200 / k * 1.1;
    svg.style.setProperty("--lid", lidFor(svg, near));
  });
}
const lidFor = (svg, near = false) => ({ ok: near ? .2 : .48, alerta: .04, perdido: .22 }[svg.dataset.mood] ?? .48);
addEventListener("pointermove", (e) => { px = e.clientX; py = e.clientY; raf ||= requestAnimationFrame(aim); }, { passive: true });
addEventListener("pointerdown", (e) => { px = e.clientX; py = e.clientY; raf ||= requestAnimationFrame(aim); }, { passive: true });

// parpadeo: de vez en cuando, cada mascota por su cuenta
function blink() {
  if (!reduced) live.forEach((svg) => { if (svg._vis && Math.random() < .7) { svg.classList.add("is-blink"); setTimeout(() => svg.classList.remove("is-blink"), 140); } });
  setTimeout(blink, 2600 + Math.random() * 2800);
}
setTimeout(blink, 1800);

// en la 404 los ojos buscan por todas partes
function wander(svg) {
  if (reduced) return;
  setInterval(() => {
    const look = Math.random() < .55, a = look ? Math.PI / 2 + (Math.random() - .5) * 1.2 : Math.random() * Math.PI * 2, d = 2.5 + Math.random() * 3;
    $$(".ag__pupil", svg).forEach((p) => (p.style.transform = `translate(${(Math.cos(a) * d).toFixed(2)}px, ${(Math.sin(a) * d * .8).toFixed(2)}px)`));
  }, 900);
}

function setMood(svg, mood) { svg.dataset.mood = mood; svg.style.setProperty("--lid", lidFor(svg)); }

/* ---------------------------------------------------------------- avisos sin leer (de la página) */
const unread = () => { const b = $("[data-unread]"); return b ? parseInt(b.textContent, 10) || 0 : 0; };
const isApp = document.body.classList.contains("has-tabs"); // páginas con sesión iniciada

/* ---------------------------------------------------------------- 404 */
const host404 = $("[data-mascot-404]");
if (host404) {
  host404.innerHTML = aguacate("perdido", "ag--hero", "mapa");
  const svg = $(".ag", host404); track(svg); wander(svg);
  const p = $("[data-404-path]"); if (p) p.textContent = location.pathname.split("/").pop() || "/";
  return; // en la 404 la mascota es la protagonista: sin pie ni avisos
}

/* ---------------------------------------------------------------- pie de página */
// En Reflex la página puede cambiar sin recargar: quita el pie y el aviso de la anterior.
document.querySelectorAll("footer.mf, .mpeek").forEach((n) => n.remove());
const foot = document.createElement("footer");
foot.className = "mf";
foot.innerHTML = `
  <div class="mf__top">
    <nav class="mf__col" aria-label="Explorar"><p class="mf__h">Explorar</p><a href="/dashboard">Panel</a><a href="/parcelas">Parcelas</a><a href="/alertas">Alertas</a><a href="/#api">API</a></nav>
    <nav class="mf__col" aria-label="Proyecto"><p class="mf__h">Proyecto</p><a href="/#codigo">Código en GitHub</a><a href="/#codigo">Licencia GPL v3</a><a href="/">Equipo Who is Json</a></nav>
    <a class="mf__word" href="/">Demeter</a>
    <div class="mf__col"><p class="mf__h">Reto</p><span>II Reto Agrotech 2026</span><span>Asociación Granada +</span></div>
    <div class="mf__col"><p class="mf__h">Finca</p><span>La Costa · Carchuna</span><span>Motril, Granada</span></div>
  </div>
  <div class="mf__stage">
    <p class="mf__status" aria-live="polite"></p>
    ${isApp ? `<button class="mf__demo" type="button" data-mascot-demo>Simular alerta (demo)</button>` : ""}
    <div class="mf__pit">${aguacate("ok", "ag--foot")}</div>
  </div>
  <p class="mf__legal mono">© 2026 Who is Json · Software libre bajo GPL v3</p>`;
const before = $(".tabs") || $(".pnav") || null;
if (before) before.parentNode.insertBefore(foot, before); else document.body.appendChild(foot);
const footAg = $(".ag", foot); track(footAg);
const status = $(".mf__status", foot);
function refreshFoot() {
  const n = unread();
  setMood(footAg, n ? "alerta" : "ok");
  status.innerHTML = n
    ? `<i class="is-warn"></i>${n} aviso${n > 1 ? "s" : ""} sin leer · <a href="/alertas">Ver alertas</a>`
    : `<i></i>Todo en orden en Finca La Costa`;
}
refreshFoot();
// si se marcan avisos como vistos (o entra uno nuevo), la mascota cambia de cara
const badge = $("[data-unread]");
if (badge) new MutationObserver(refreshFoot).observe(badge, { childList: true, characterData: true, subtree: true });

/* ---------------------------------------------------------------- aviso de alerta nueva */
// Reglas para que no moleste: solo alertas graves, como mucho una cada 3 min,
// si llegan varias mientras está a la vista se agrupan, y se va sola a los 10 s.
if (!isApp) return;
const GAP = 3 * 60e3, SHOW = 10e3;
const NEW = [
  { k: "Bancal 3", t: "Humedad del suelo al 17 %", s: "Mínimo 25 %. Conviene regar antes de las 11:00." },
  { k: "Invernadero", t: "Temperatura a 36,2 ºC", s: "Máximo 35 ºC. Abre la ventilación cenital." },
  { k: "Bancal 1", t: "Humedad ambiente al 88 %", s: "Máximo 85 %. Riesgo de hongos en el aguacate." },
];
const store = { get() { try { return +sessionStorage.getItem("mascota:ultimo") || 0; } catch { return store._m || 0; } },
                set(v) { try { sessionStorage.setItem("mascota:ultimo", v); } catch { store._m = v; } } };

const peek = document.createElement("div");
peek.className = "mpeek"; peek.hidden = true;
peek.innerHTML = `
  <div class="mpeek__bubble" role="status" aria-live="polite">
    <p class="mpeek__k mono"></p><p class="mpeek__t"></p><p class="mpeek__s"></p><p class="mpeek__more mono"></p>
    <div class="mpeek__act"><a class="mpeek__go" href="/alertas">Ver alerta</a><button type="button" class="mpeek__no">Ahora no</button></div>
  </div>
  <div class="mpeek__pit">${aguacate("alerta", "ag--peek", "senal")}</div>`;
document.body.appendChild(peek);
const peekAg = $(".ag", peek); track(peekAg);
let shown = 0, timer = 0, i = 0;

function hide() {
  clearTimeout(timer);
  peek.classList.remove("is-in");
  setTimeout(() => { if (!peek.classList.contains("is-in")) peek.hidden = true; }, reduced ? 0 : 420);
}
function arm() { clearTimeout(timer); timer = setTimeout(hide, SHOW); }

function newAlert(force = false) {
  const a = NEW[i++ % NEW.length];
  $$("[data-unread]").forEach((b) => (b.textContent = (parseInt(b.textContent, 10) || 0) + 1));
  if (peek.classList.contains("is-in")) {      // ya está a la vista: agrupa
    shown++; $(".mpeek__k", peek).textContent = `${shown} alertas nuevas`;
    $(".mpeek__more", peek).textContent = `+ ${a.t.toLowerCase()} · ${a.k}`;
    $(".mpeek__go", peek).textContent = "Ver alertas";
    peekAg.classList.remove("is-jolt"); void peekAg.offsetWidth; peekAg.classList.add("is-jolt");
    arm(); return;
  }
  if (!force && Date.now() - store.get() < GAP) return; // hace poco que avisó: solo sube el contador
  store.set(Date.now());
  shown = 1;
  $(".mpeek__k", peek).textContent = `Alerta nueva · ${a.k}`;
  $(".mpeek__t", peek).textContent = a.t;
  $(".mpeek__s", peek).textContent = a.s;
  $(".mpeek__more", peek).textContent = "";
  $(".mpeek__go", peek).textContent = "Ver alerta";
  peek.hidden = false; void peek.offsetWidth; peek.classList.add("is-in");
  arm();
}
peek.addEventListener("pointerenter", () => clearTimeout(timer));
peek.addEventListener("pointerleave", arm);
peek.addEventListener("focusin", () => clearTimeout(timer));
$(".mpeek__no", peek).addEventListener("click", hide);
addEventListener("keydown", (e) => { if (e.key === "Escape" && !peek.hidden) hide(); });
$("[data-mascot-demo]")?.addEventListener("click", () => newAlert(true));

// en el prototipo, el simulador de sensores "dispara" una alerta a los 8 s de entrar
setTimeout(() => newAlert(false), 8000);
})();
