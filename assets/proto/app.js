// Demeter · interacción de las páginas de la app (prototipo con datos de ejemplo).
// Cada bloque arranca solo si su página lo tiene: [data-twin], [data-map], [data-timeline], [data-thr-editor]…
(() => {
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
// es-ES no separa los miles de 4 cifras (2400); para leer litros de un vistazo, sí: 2.400
const fmt = (v, d = 0) => v.toLocaleString("es-ES", { minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: "always" });
const easeOut = (t) => 1 - Math.pow(1 - t, 3);
const NOW = new Date(2026, 10, 16, 11, 2);

/* ---------------------------------------------------------------- datos de ejemplo */
const SENS = [
  { id: "h001", n: "Humedad del suelo", s: "Suelo", u: "%", d: 0, lo: 25, hi: 60, layer: "suelo" },
  { id: "t001", n: "Temperatura", s: "Aire", u: "ºC", d: 1, lo: 10, hi: 35, layer: "temperatura" },
  { id: "l001", n: "Luminosidad", s: "Luz", u: "klx", d: 0, lo: 5, hi: 90, layer: "luz" },
  { id: "a001", n: "Humedad ambiente", s: "Humedad", u: "%", d: 0, lo: 40, hi: 85, layer: "aire" },
];
const byId = Object.fromEntries(SENS.map((x) => [x.id, x]));
let seed = 3;
const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
/** Serie horaria de `hours` horas hasta ahora (la última es la lectura actual). */
function series(id, hours) {
  seed = id.charCodeAt(0) * 97 + hours;
  const out = [];
  for (let i = hours; i >= 0; i--) {
    const h = (NOW.getHours() - i % 24 + 48) % 24, day = Math.sin(((h - 7) / 24) * Math.PI * 2), n = (rnd() - 0.5);
    let v;
    if (id === "t001") v = 19 + 6 * day + n * 0.8;
    else if (id === "l001") v = Math.max(0, 48 * Math.sin(((h - 7) / 13) * Math.PI)) * (h > 6 && h < 20 ? 1 : 0) + Math.abs(n);
    else if (id === "a001") v = 68 - 13 * day + n * 2;
    else { const since = i % 62; v = 19 + since * 0.42 + n * 0.6; } // riego cada ~62 h; ahora, 19 %
    out.push(v);
  }
  const fix = { t001: 23.7, l001: 42, a001: 61, h001: 19 }[id];
  out[out.length - 1] = fix;
  return out;
}
const current = (id) => { const a = series(id, 1); return a[a.length - 1]; };
const status = (x, v) => (v < x.lo ? "bajo" : v > x.hi ? "alto" : "ok");
const hourLabel = (hoursAgo) => { const d = new Date(NOW - hoursAgo * 3600e3); return `${d.getDate()}/${d.getMonth() + 1} ${String(d.getHours()).padStart(2, "0")}:00`; };

/* ---------------------------------------------------------------- aviso emergente */
function toast(msg) {
  const t = $(".toast"); if (!t) return;
  t.textContent = msg; t.hidden = false;
  clearTimeout(t._h); t._h = setTimeout(() => (t.hidden = true), 2800);
}

/* ---------------------------------------------------------------- cifra que rueda hasta su valor */
function roll(el, to, d = 0) {
  const from = parseFloat(el.dataset.v ?? to);
  el.dataset.v = to;
  if (reduced || from === to) { el.textContent = fmt(to, d); return; }
  const t0 = performance.now();
  const step = (t) => { const k = Math.min(1, (t - t0) / 450); el.textContent = fmt(from + (to - from) * easeOut(k), d); if (k < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}

/* ---------------------------------------------------------------- gráfica con cursor */
// Dibuja `data` con la franja de umbrales; al pasar el ratón (o el dedo) muestra hora y valor.
function chart(host, { data, lo, hi, unit = "", d = 0, label = (i) => "", proj = null, height = 220 }) {
  const W = 1000, H = height, pad = 10;
  const all = proj ? data.concat(proj) : data;
  let mn = Math.min(...all, lo ?? Infinity), mx = Math.max(...all, hi ?? -Infinity);
  const span = mx - mn || 1; mn -= span * 0.08; mx += span * 0.08;
  const n = data.length + (proj ? proj.length - 1 : 0);
  const X = (i) => (i / (n - 1)) * W, Y = (v) => pad + (1 - (v - mn) / (mx - mn)) * (H - 2 * pad);
  const line = (arr, off = 0) => arr.map((v, i) => `${X(i + off).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
  const band = lo != null && hi != null ? `<rect class="c-band" x="0" y="${Y(Math.min(hi, mx))}" width="${W}" height="${Math.max(0, Y(Math.max(lo, mn)) - Y(Math.min(hi, mx)))}"/>` : "";
  const ths = [lo, hi].filter((v) => v != null && v > mn && v < mx).map((v) => `<line class="c-th" x1="0" x2="${W}" y1="${Y(v)}" y2="${Y(v)}"/>`).join("");
  host.innerHTML = `<div class="c-wrap"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="height:${H}px" role="img" aria-label="Gráfica de ${data.length} lecturas">
      ${band}${ths}
      <polygon class="c-area" points="0,${H} ${line(data)} ${X(data.length - 1)},${H}"/>
      <polyline class="c-line" points="${line(data)}"/>
      ${proj ? `<polyline class="c-proj" points="${line(proj, data.length - 1)}"/>` : ""}
      <line class="c-x" x1="0" x2="0" y1="0" y2="${H}"/></svg>
    <span class="c-dot"></span><span class="c-now"></span>
    <div class="c-tip"><b></b><small></small></div></div>`;
  const wrap = $(".c-wrap", host), dot = $(".c-dot", host), tip = $(".c-tip", host), xl = $(".c-x", host), now = $(".c-now", host);
  const place = (el, i, v) => { el.style.left = `${(X(i) / W) * 100}%`; el.style.top = `${(Y(v) / H) * 100}%`; };
  place(now, data.length - 1, data[data.length - 1]);
  const show = (e) => {
    const r = wrap.getBoundingClientRect(), f = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    const i = Math.round(f * (n - 1)), isProj = i >= data.length, v = isProj ? proj[i - data.length + 1] : data[i];
    wrap.classList.add("is-on");
    place(dot, i, v); xl.setAttribute("x1", X(i)); xl.setAttribute("x2", X(i));
    tip.style.left = `${Math.min(88, Math.max(12, f * 100))}%`;
    $("b", tip).textContent = `${fmt(v, d)} ${unit}`;
    $("small", tip).textContent = isProj ? `previsto · ${label(i)}` : label(i);
    tip.classList.toggle("is-proj", isProj);
  };
  wrap.addEventListener("pointermove", show);
  wrap.addEventListener("pointerdown", show);
  wrap.addEventListener("pointerleave", () => wrap.classList.remove("is-on"));
  if (!reduced && !host.dataset.drawn) { host.dataset.drawn = "1"; $("svg", host).animate([{ clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0 0 0)" }], { duration: 900, easing: "cubic-bezier(.23,1,.32,1)" }); }
}

/* ---------------------------------------------------------------- clics generales */
document.addEventListener("click", (e) => {
  const pill = e.target.closest("[data-group] > .pill");
  if (pill) pill.parentElement.querySelectorAll(".pill").forEach((p) => p.setAttribute("aria-pressed", String(p === pill)));
  const msg = e.target.closest("[data-toast]");
  if (msg) toast(msg.dataset.toast);
  if (e.target.closest('a[href="#"]')) e.preventDefault();
});

/* ================================================================ ENTRAR */
const form = $("[data-login]");
if (form) {
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const u = form.username.value.trim(), p = form.password.value, err = $(".login__err", form), btn = $("button", form);
    if (!u || !p) { err.textContent = "Escribe tu usuario y tu contraseña."; return; }
    err.textContent = ""; btn.disabled = true; btn.textContent = "Entrando…";
    setTimeout(() => {
      if (p === "demo1234") location.href = "/dashboard";
      else { btn.disabled = false; btn.textContent = "Entrar"; err.textContent = "Usuario o contraseña incorrectos."; }
    }, 600);
  });
  // lecturas que van pasando por la ventana
  const cap = $("[data-ticker]"), lines = ["Invernadero 2 · Carchuna · aire 27,4 ºC", "Bancal 3 · Almuñécar · suelo 19 %", "Cortijo Los Llanos · luz 42 klx", "Depósito norte · 68 % · 41 m³"];
  let k = 0; if (cap && !reduced) setInterval(() => { cap.classList.add("is-out"); setTimeout(() => { cap.lastChild.textContent = lines[++k % lines.length]; cap.classList.remove("is-out"); }, 220); }, 2600);
}

/* ================================================================ PANEL */
const twin = $("[data-twin]");
if (twin) {
  let sel = "h001";
  const ro = { name: $("[data-ro-name]"), v: $("[data-ro-v]"), u: $("[data-ro-u]"), st: $("[data-ro-st]"), band: $("[data-ro-band]"), dot: $("[data-ro-dot]"), lo: $("[data-ro-lo]"), hi: $("[data-ro-hi]"), chart: $("[data-ro-chart]") };
  const live = Object.fromEntries(SENS.map((x) => [x.id, series(x.id, 24)]));
  // Capas: color de cada terraza (de delante a atrás) según su lectura.
  const LAYERS = {
    suelo: { vals: [44, 36, 19, 28], lo: 25, hi: 60 },
    temperatura: { vals: [22.1, 23, 23.7, 24.6], lo: 10, hi: 35 },
    luz: { vals: [38, 42, 44, 47], lo: 5, hi: 90 },
    aire: { vals: [64, 62, 61, 59], lo: 40, hi: 85 },
  };
  const ramp = (v, lo, hi) => (v < lo ? "#c2522d" : v > hi ? "#c2522d" : (v - lo) / (hi - lo) < 0.25 ? "#e3a07c" : "#7fa69a");
  function setLayer(name) {
    const L = LAYERS[name];
    twin.dispatchEvent(new CustomEvent("twin:layer", { detail: L.vals.map((v) => ramp(v, L.lo, L.hi)) }));
    $$("[data-layer]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.layer === name)));
    $("[data-legend]").innerHTML = L.vals.map((v, i) => `<span><i style="background:${ramp(v, L.lo, L.hi)}"></i>Bancal ${i + 1} · ${fmt(v, name === "temperatura" ? 1 : 0)}</span>`).join("");
  }
  function select(id) {
    sel = id;
    const x = byId[id], data = live[id], v = data[data.length - 1], st = status(x, v);
    ro.name.textContent = x.n;
    roll(ro.v, v, x.d);
    ro.u.textContent = x.u;
    ro.st.textContent = st === "ok" ? "Dentro de su margen" : st === "bajo" ? `Por debajo de ${x.lo} ${x.u}` : `Por encima de ${x.hi} ${x.u}`;
    $(".ro").classList.toggle("is-warn", st !== "ok");
    const sc = { min: 0, max: x.u === "ºC" ? 45 : x.u === "klx" ? 110 : 100 }, pc = (q) => ((q - sc.min) / (sc.max - sc.min)) * 100;
    ro.band.style.left = pc(x.lo) + "%"; ro.band.style.width = pc(x.hi) - pc(x.lo) + "%";
    ro.dot.style.left = pc(v) + "%";
    ro.lo.textContent = `${x.lo} ${x.u}`; ro.hi.textContent = `${x.hi} ${x.u}`;
    chart(ro.chart, { data, lo: x.lo, hi: x.hi, unit: x.u, d: x.d, label: (i) => hourLabel(data.length - 1 - i), height: 120 });
    $$("[data-pick]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.pick === id)));
    $$(".tw__pin").forEach((p) => p.classList.toggle("is-sel", p.dataset.sensor === id));
    setLayer(x.layer);
  }
  twin.addEventListener("twin:pick", (e) => select(e.detail));
  $$("[data-pick]").forEach((b) => b.addEventListener("click", () => select(b.dataset.pick)));
  $$("[data-layer]").forEach((b) => b.addEventListener("click", () => { const s = SENS.find((q) => q.layer === b.dataset.layer); select(s.id); }));
  // espera a que el gemelo haya creado los botones
  requestAnimationFrame(() => select(sel));

  // En directo: cada 3 s llega una lectura nueva del sensor elegido.
  if (!reduced) setInterval(() => {
    const x = byId[sel], arr = live[sel], last = arr[arr.length - 1];
    const nv = Math.round((last + (Math.random() - 0.5) * (x.d ? 0.4 : 1.2)) * 10 ** x.d) / 10 ** x.d;
    arr.push(nv); arr.shift();
    roll(ro.v, nv, x.d);
    $$("[data-ago]").forEach((el) => (el.textContent = "ahora"));
    chart(ro.chart, { data: arr, lo: x.lo, hi: x.hi, unit: x.u, d: x.d, label: (i) => hourLabel(arr.length - 1 - i), height: 120 });
  }, 3000);

  // Simulador de riego: minutos → litros → humedad prevista a las 12:00.
  const irr = $("[data-irr]");
  const soil = series("h001", 18);
  const draw = () => {
    const min = Number(irr.value), litros = min * 96, gain = min * 0.52;
    $("[data-irr-min]").textContent = min;
    roll($("[data-irr-l]"), litros, 0);
    const to = 19 + gain - 0.4;
    roll($("[data-irr-to]"), to, 0);
    $("[data-irr-to]").closest(".irr__out").classList.toggle("is-ok", to >= 25);
    const proj = [19]; for (let h = 1; h <= 6; h++) proj.push(h === 1 ? 19 + gain * 0.7 : 19 + gain - h * 0.12);
    chart($("[data-irr-chart]"), { data: soil, proj, lo: 25, hi: 60, unit: "%", label: (i) => (i < soil.length ? hourLabel(soil.length - 1 - i) : `+${i - soil.length + 1} h`), height: 130 });
    irr.style.setProperty("--f", `${(min / Number(irr.max)) * 100}%`);
  };
  irr.addEventListener("input", draw);
  draw();
  const go = $("[data-irr-go]");
  go.addEventListener("click", () => {
    if (go.dataset.busy) return;
    go.dataset.busy = "1"; go.classList.add("is-busy");
    setTimeout(() => { go.classList.remove("is-busy"); go.classList.add("is-done"); go.lastChild.textContent = "Programado 10:35"; toast(`Riego del Bancal 3 programado · 10:35 · ${irr.value} min`); }, 1100);
  });
  // cuenta atrás hasta las 11:00 (en la demo: minutos que faltan desde la hora real)
  const cd = $("[data-count]");
  // reloj de la demo: son las 9:48 al abrir la página y el tiempo corre de verdad
  const t0 = Date.now(), tick = () => { const m = Math.max(0, 72 - Math.floor((Date.now() - t0) / 60000)); cd.textContent = `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`; };
  tick(); setInterval(tick, 30000);

  // Gráfica grande de abajo: el sensor que elijas en las pestañas.
  const big = $("[data-chart-main]");
  const drawBig = (id) => { const x = byId[id], data = series(id, 72); chart(big, { data, lo: x.lo, hi: x.hi, unit: x.u, d: x.d, label: (i) => hourLabel(data.length - 1 - i), height: 260 }); };
  $$("[data-main]").forEach((b) => b.addEventListener("click", () => drawBig(b.dataset.main)));
  drawBig("h001");
}

/* ================================================================ PARCELAS */
const map = $("[data-map]");
if (map) {
  const P = [
    { id: "costa", name: "Finca La Costa", where: "Carchuna, Motril", ha: "1,2 ha", crop: "Invernadero", img: "/proto/img/mundos/medir.webp", x: 0.33, y: 0.71, warn: true, n: 4, poly: [[-40, -18], [44, -26], [52, 16], [-34, 24]] },
    { id: "rio", name: "Bancales del Río Verde", where: "Almuñécar", ha: "3,4 ha", crop: "Aguacate", img: "/proto/img/mundos/avisar.webp", x: 0.72, y: 0.49, n: 6, poly: [[-50, -30], [40, -36], [58, 20], [-42, 34]] },
    { id: "llanos", name: "Cortijo Los Llanos", where: "Lújar", ha: "0,8 ha", crop: "Chirimoya", img: "/proto/img/mundos/regar.webp", x: 0.5, y: 0.27, n: 2, poly: [[-26, -16], [30, -20], [34, 14], [-24, 18]] },
  ];
  // Curvas de nivel: anillos deformados alrededor de tres cerros; el mar abajo.
  const W = 1000, H = 640;
  const hills = [[620, 150, 1], [300, 120, 0.8], [880, 300, 0.7]];
  let contours = "";
  hills.forEach(([cx, cy, k], hi) => {
    for (let r = 26; r < 420 * k; r += 26) {
      let d = "";
      for (let a = 0; a <= 64; a++) {
        const t = (a / 64) * Math.PI * 2, w = 1 + 0.12 * Math.sin(t * 3 + hi) + 0.07 * Math.sin(t * 7 + r * 0.05);
        const x = cx + Math.cos(t) * r * 1.5 * w, y = cy + Math.sin(t) * r * 0.82 * w;
        d += (a ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
      }
      contours += `<path class="m-c${r % 104 === 0 ? " m-c--major" : ""}" d="${d}Z"/>`;
    }
  });
  const coast = "M0 560 C120 540 200 590 330 575 S520 520 640 548 S860 600 1000 560 L1000 640 L0 640Z";
  const parcels = P.map((p) => {
    const cx = p.x * W, cy = p.y * H;
    return `<g class="m-p${p.warn ? " is-warn" : ""}" data-id="${p.id}" tabindex="0" role="button" aria-label="${p.name}">
      <polygon points="${p.poly.map(([a, b]) => `${cx + a},${cy + b}`).join(" ")}"/>
      <circle class="m-ping" cx="${cx}" cy="${cy}" r="7"/><circle class="m-pin" cx="${cx}" cy="${cy}" r="5"/></g>`;
  }).join("");
  map.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid slice" aria-label="Mapa de las fincas en la Costa Tropical">
      <rect width="${W}" height="${H}" class="m-bg"/>${contours}<path class="m-sea" d="${coast}"/>
      <text class="m-lbl" x="140" y="615">Mar Mediterráneo</text><text class="m-lbl" x="520" y="90">Sierra de Lújar</text><text class="m-lbl" x="150" y="520">Motril</text><text class="m-lbl" x="740" y="530">Almuñécar</text>
      ${parcels}</svg><div class="m-card" hidden></div>`;
  const card = $(".m-card", map);
  const showCard = (p) => {
    card.innerHTML = `<img src="${p.img}" alt=""><b>${p.name}</b><small>${p.where} · ${p.ha} · ${p.crop}</small><span class="${p.warn ? "is-warn" : ""}">${p.warn ? "1 sensor bajo" : "Todo en margen"}</span>`;
    card.style.left = `${p.x * 100}%`; card.style.top = `${p.y * 100}%`; card.hidden = false;
  };
  function pick(id) {
    const p = P.find((q) => q.id === id);
    $$(".m-p", map).forEach((g) => g.classList.toggle("is-sel", g.dataset.id === id));
    $$("[data-parcel]").forEach((r) => r.setAttribute("aria-current", String(r.dataset.parcel === id)));
    $$("[data-parcel-name]").forEach((el) => (el.textContent = p.name));
    drawHist();
  }
  $$(".m-p", map).forEach((g) => {
    const p = P.find((q) => q.id === g.dataset.id);
    g.addEventListener("pointerenter", () => showCard(p));
    g.addEventListener("pointerleave", () => (card.hidden = true));
    g.addEventListener("click", () => pick(p.id));
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(p.id); } });
  });
  $$("[data-parcel]").forEach((r) => {
    r.addEventListener("click", () => pick(r.dataset.parcel));
    r.addEventListener("pointerenter", () => { const p = P.find((q) => q.id === r.dataset.parcel); showCard(p); $$(".m-p", map).forEach((g) => g.classList.toggle("is-hover", g.dataset.id === p.id)); });
    r.addEventListener("pointerleave", () => { card.hidden = true; $$(".m-p", map).forEach((g) => g.classList.remove("is-hover")); });
  });

  // Histórico: sensor × rango → gráfica, cifras y tabla.
  let hs = "h001", hr = 24;
  function drawHist() {
    const x = byId[hs], data = series(hs, hr);
    const step = hr > 168 ? 24 : hr > 24 ? 6 : 1;
    chart($("[data-chart-hist]"), { data, lo: x.lo, hi: x.hi, unit: x.u, d: x.d, label: (i) => hourLabel(data.length - 1 - i), height: 300 });
    const mn = Math.min(...data), mx = Math.max(...data), avg = data.reduce((a, b) => a + b, 0) / data.length, out = data.filter((v) => status(x, v) !== "ok").length;
    $("[data-stats]").innerHTML = [["Mínimo", mn], ["Media", avg], ["Máximo", mx]].map(([k, v]) => `<div><small>${k}</small><b>${fmt(v, x.d)}<i>${x.u}</i></b></div>`).join("") + `<div class="${out ? "is-warn" : ""}"><small>Fuera de margen</small><b>${out}<i>h</i></b></div>`;
    const rows = []; for (let i = data.length - 1; i >= 0 && rows.length < 6; i -= step) rows.push(`<tr><td class="mono">${hourLabel(data.length - 1 - i)}</td><td>${fmt(data[i], x.d)} ${x.u}</td><td>${x.lo}–${x.hi} ${x.u}</td><td class="${status(x, data[i]) !== "ok" ? "warn" : ""}">${{ ok: "Normal", bajo: "Bajo", alto: "Alto" }[status(x, data[i])]}</td></tr>`);
    $("[data-hist-table]").innerHTML = rows.join("");
    $("[data-csv]").dataset.toast = `Descargando ${hs}_${hr}h.csv · ${data.length} lecturas`;
  }
  $$("[data-hs]").forEach((b) => b.addEventListener("click", () => { hs = b.dataset.hs; drawHist(); }));
  $$("[data-hr]").forEach((b) => b.addEventListener("click", () => { hr = Number(b.dataset.hr); drawHist(); }));
  // mini-gráficas de las filas
  $$("[data-spark]").forEach((s) => { const a = series("h001", 24).map((v, i) => v + Number(s.dataset.spark) * 6 + Math.sin(i / 3) * 2); const mn = Math.min(...a), mx = Math.max(...a); s.innerHTML = `<polyline points="${a.map((v, i) => `${(i / 24) * 100},${2 + (1 - (v - mn) / (mx - mn)) * 26}`).join(" ")}"/>`; });
  pick("costa");
}

/* ================================================================ ALERTAS */
const tl = $("[data-timeline]");
if (tl) {
  const A = [
    { h: 0.15, id: "h001", k: "bajo", t: "Humedad del suelo al 19 %", sub: "Bancal 3 · mínimo 25 %", seen: false, act: "Regar 25 min antes de las 11:00" },
    { h: 19.4, id: "t001", k: "alto", t: "Temperatura a 36 ºC", sub: "Invernadero · máximo 35 ºC", seen: false, act: "Abrir ventanas cenitales" },
    { h: 51, id: "a001", k: "bajo", t: "Humedad ambiente al 38 %", sub: "Bancal 1 · mínimo 40 %", seen: true },
    { h: 70, id: "l001", k: "alto", t: "Luminosidad a 93 klx", sub: "Bancal 4 · máximo 90 klx", seen: true },
    { h: 98, id: "h001", k: "bajo", t: "Humedad del suelo al 23 %", sub: "Bancal 3 · mínimo 25 %", seen: true },
    { h: 131, id: "t001", k: "alto", t: "Temperatura a 35,6 ºC", sub: "Invernadero · máximo 35 ºC", seen: true },
  ];
  const SPAN = 168;
  // eje de 7 días con un punto por aviso
  let ticks = ""; for (let d = 0; d <= 7; d++) { const dt = new Date(NOW - d * 864e5); ticks += `<span class="t-tick" style="left:${100 - (d / 7) * 100}%">${d === 0 ? "hoy" : dt.toLocaleDateString("es-ES", { weekday: "short", day: "numeric" })}</span>`; }
  tl.innerHTML = `<div class="t-axis">${ticks}${A.map((a, i) => `<button class="t-dot t-dot--${a.k}${a.seen ? " is-seen" : ""}" style="left:${100 - (a.h / SPAN) * 100}%" data-i="${i}" aria-label="${a.t}"><span>${a.t}<small>${hourLabel(a.h)}</small></span></button>`).join("")}</div>`;
  const list = $("[data-alerts]");
  list.innerHTML = A.map((a, i) => `<li class="ar${a.seen ? " is-seen" : ""}" data-i="${i}" data-seen="${a.seen ? 1 : 0}">
      <span class="ar__k ar__k--${a.k}">${a.k === "bajo" ? "↓" : "↑"}</span>
      <span class="ar__t"><b>${a.t}</b><small>${byId[a.id].n} · ${a.id} · ${a.sub}</small>${a.act ? `<em>${a.act}</em>` : ""}</span>
      <time>${a.h < 1 ? `hace ${Math.round(a.h * 60)} min` : a.h < 24 ? `hace ${Math.round(a.h)} h` : hourLabel(a.h)}</time>
      <span class="ar__act">${a.seen ? `<span class="mono">vista</span>` : `<button class="pill pill--s" type="button" data-seen-btn>Marcar vista</button>`}<a class="pill pill--s" href="/parcelas">Ver sensor</a></span></li>`).join("");
  const count = () => { const n = $$('.ar[data-seen="0"]', list).length; $$("[data-unread]").forEach((el) => (el.textContent = n || "")); $("[data-unread-big]").textContent = n; };
  count();
  list.addEventListener("click", (e) => {
    const b = e.target.closest("[data-seen-btn]"); if (!b) return;
    const row = b.closest(".ar"), i = row.dataset.i;
    row.classList.add("is-leaving");
    setTimeout(() => {
      row.classList.remove("is-leaving"); row.classList.add("is-seen"); row.dataset.seen = "1";
      b.outerHTML = `<span class="mono">vista</span>`;
      $(`.t-dot[data-i="${i}"]`, tl).classList.add("is-seen");
      count(); toast("Alerta marcada como vista");
    }, 260);
  });
  tl.addEventListener("click", (e) => {
    const d = e.target.closest(".t-dot"); if (!d) return;
    const row = $(`.ar[data-i="${d.dataset.i}"]`, list); row.hidden = false;
    row.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "center" });
    row.classList.remove("is-flash"); void row.offsetWidth; row.classList.add("is-flash");
  });
  $$("[data-filter]").forEach((b) => b.addEventListener("click", () => {
    $$(".ar", list).forEach((r) => (r.hidden = b.dataset.filter === "unread" && r.dataset.seen === "1"));
  }));
  $("[data-all-seen]").addEventListener("click", () => { $$('.ar[data-seen="0"] [data-seen-btn]', list).forEach((b) => b.click()); });
}

/* ================================================================ AJUSTES */
const thrHost = $("[data-thr-editor]");
if (thrHost) {
  const RANGE = { "ºC": [0, 45], "%": [0, 100], klx: [0, 110] };
  thrHost.innerHTML = SENS.map((x) => `<div class="te" data-id="${x.id}">
      <div class="te__h"><span class="te__name">${x.n}<small>${x.id} · últimos 7 días</small></span>
        <span class="te__vals"><b data-lo>${x.lo}</b><i>–</i><b data-hi>${x.hi}</b><small>${x.u}</small></span>
        <span class="te__n" data-n></span></div>
      <div class="te__track"><div class="te__bars"></div><div class="te__band"></div>
        <button class="te__h1" type="button" role="slider" aria-label="Umbral bajo de ${x.n}" data-h="lo"></button>
        <button class="te__h2" type="button" role="slider" aria-label="Umbral alto de ${x.n}" data-h="hi"></button></div>
      <div class="te__axis"><span>${RANGE[x.u][0]} ${x.u}</span><span>${RANGE[x.u][1]} ${x.u}</span></div></div>`).join("");
  $$(".te", thrHost).forEach((el) => {
    const x = byId[el.dataset.id], [r0, r1] = RANGE[x.u], data = series(x.id, 168), BINS = 40;
    const hist = Array(BINS).fill(0); data.forEach((v) => hist[Math.min(BINS - 1, Math.max(0, Math.floor(((v - r0) / (r1 - r0)) * BINS)))]++);
    const mxh = Math.max(...hist);
    const bars = $(".te__bars", el);
    bars.innerHTML = hist.map((c, i) => `<i style="height:${c ? 8 + (c / mxh) * 92 : 0}%" data-b="${i}"></i>`).join("");
    const st = { lo: x.lo, hi: x.hi };
    const pc = (v) => ((v - r0) / (r1 - r0)) * 100;
    const paint = () => {
      $(".te__h1", el).style.left = pc(st.lo) + "%"; $(".te__h2", el).style.left = pc(st.hi) + "%";
      $(".te__band", el).style.left = pc(st.lo) + "%"; $(".te__band", el).style.width = pc(st.hi) - pc(st.lo) + "%";
      $(".te__h1", el).setAttribute("aria-valuenow", st.lo); $(".te__h2", el).setAttribute("aria-valuenow", st.hi);
      $("[data-lo]", el).textContent = st.lo; $("[data-hi]", el).textContent = st.hi;
      $$("i", bars).forEach((b) => { const v = r0 + ((Number(b.dataset.b) + 0.5) / BINS) * (r1 - r0); b.classList.toggle("is-out", v < st.lo || v > st.hi); });
      // cada vez que la lectura cruza el umbral = un aviso
      let n = 0, prev = true; data.forEach((v) => { const ok = v >= st.lo && v <= st.hi; if (!ok && prev) n++; prev = ok; });
      const nEl = $("[data-n]", el); nEl.textContent = n === 0 ? "Ningún aviso esta semana" : n === 1 ? "1 aviso esta semana" : `${n} avisos esta semana`;
      nEl.classList.toggle("is-warn", n > 3);
      el.dataset.dirty = String(st.lo !== x.lo || st.hi !== x.hi);
    };
    paint();
    // arrastrar las asas (o flechas del teclado)
    $$("[data-h]", el).forEach((h) => {
      const which = h.dataset.h;
      h.addEventListener("pointerdown", (e) => {
        h.setPointerCapture(e.pointerId); h.classList.add("is-drag");
        const track = $(".te__track", el).getBoundingClientRect();
        const move = (ev) => {
          let v = Math.round(r0 + ((ev.clientX - track.left) / track.width) * (r1 - r0));
          v = which === "lo" ? Math.min(Math.max(r0, v), st.hi - 1) : Math.max(Math.min(r1, v), st.lo + 1);
          if (v !== st[which]) { st[which] = v; paint(); }
        };
        const up = () => { h.removeEventListener("pointermove", move); h.classList.remove("is-drag"); };
        h.addEventListener("pointermove", move); h.addEventListener("pointerup", up, { once: true }); h.addEventListener("pointercancel", up, { once: true });
      });
      h.addEventListener("keydown", (e) => {
        const dv = e.key === "ArrowRight" || e.key === "ArrowUp" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowDown" ? -1 : 0;
        if (!dv) return; e.preventDefault();
        st[which] = which === "lo" ? Math.min(Math.max(r0, st.lo + dv), st.hi - 1) : Math.max(Math.min(r1, st.hi + dv), st.lo + 1);
        paint();
      });
    });
  });
  $("[data-thr-save]").addEventListener("click", () => {
    const n = $$('.te[data-dirty="true"]', thrHost).length;
    toast(n ? `Umbrales guardados en ${n} sensor${n > 1 ? "es" : ""} · se aplican a las próximas lecturas` : "No has cambiado ningún umbral");
  });
}
})();
