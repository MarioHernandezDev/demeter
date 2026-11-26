// Demeter · cambio de tema claro ⇄ oscuro con una mancha de TINTA que sale del botón y se
// extiende deshaciéndose en vetas (réplica del efecto «ink» de codemure).
//
// El estado es el modo de color de Reflex: clase `light`/`dark` en <html> y `localStorage.theme`
// (el script que Reflex pone en el <head> lo aplica antes de pintar, así que no hay parpadeo).
//
// Cómo se hace:
//  1. Un shader WebGL2 pinta, una vez por cambio, un CAMPO de tinta en una imagen:
//       R = forma: distancia al botón deformada con ruido fractal (dedos/«tendrils», islas)
//       G = humo: volutas que se adelantan al frente (la tinta «se desvanece» en gris)
//       B = vetas: bandas finas marmoladas, paralelas al frente y retorcidas
//  2. View Transitions: el navegador congela la página con el tema viejo y debajo cambiamos el tema.
//  3. La página nueva (::view-transition-new(root)) lleva una MÁSCARA SVG con la imagen del campo
//     y, dentro, un filtro que la umbraliza; en cada fotograma solo cambian sus números:
//       tinta = kf·(nivel − R) + kv·(B − ½)      (borde casi duro, con vetas en la franja)
//       humo  = kh·(nivel − G)                    (rampa suave: volutas semitransparentes)
//       alfa  = tinta ∪ HUMO·humo
//     Lejos del frente manda R (todo viejo o todo nuevo); en el frente la tinta llega en vetas que
//     se engordan y se funden, y por delante van volutas grises: el tema viejo se desvanece.
// Sin View Transitions, sin WebGL2 o con «reducir movimiento», el cambio es instantáneo.
(() => {
  if (window.__dmTema) return;
  window.__dmTema = true;

  // ---- ajustes (los mismos mandos que el original)
  const DURACION = 2800; // ms (el frente cruza la pantalla en ~2 s; el resto, las últimas islas)
  const TENDRILS = 1.75; // cuánto se deforma el frente (dedos)
  const ESCALA_RUIDO = 1.2; // tamaño del ruido (más alto = más menudo)
  const FRANJA = 0.016; // suavidad del frente; la franja de vetas mide ~FRANJA·CONTRASTE_VETAS (1 = botón→esquina)
  const CONTRASTE_VETAS = 6; // nitidez de las vetas (más alto = bordes más finos)
  const HUMO = 0.55; // opacidad máxima de las volutas de humo que se adelantan
  const SUAVIDAD_HUMO = 0.05; // ancho de la rampa del humo (unidades de campo)
  const RES_CAMPO = 0.5; // resolución del campo respecto a la pantalla

  // R codifica el campo f ∈ [F0, F0 + FR]
  const F0 = -0.15, FR = 1.75;

  // Avance del nivel de tinta (en unidades de campo) frente al tiempo (0–1), medido fotograma a
  // fotograma en el vídeo: la gota tarda un instante, revienta, cruza la pantalla y frena mucho
  // mientras se comen las últimas islas.
  const AVANCE = [[0, -0.02], [0.05, 0.03], [0.12, 0.09], [0.22, 0.3], [0.32, 0.47], [0.42, 0.63], [0.52, 0.78],
    [0.62, 0.91], [0.72, 1.03], [0.84, 1.18], [0.93, 1.32], [1, 1.45]];

  const raiz = document.documentElement;
  const actual = () => (raiz.classList.contains("dark") ? "dark" : "light");

  let enCurso = false; // hay un cambio con tinta en marcha

  function sincronizar() {
    const oscuro = actual() === "dark";
    document.querySelectorAll("[data-tema]").forEach((b) => {
      b.setAttribute("aria-pressed", String(oscuro));
      b.setAttribute("aria-label", oscuro ? "Cambiar a modo claro" : "Cambiar a modo oscuro");
      b.title = oscuro ? "Modo claro" : "Modo oscuro";
    });
  }

  function aplicar(tema) {
    raiz.classList.remove("light", "dark");
    raiz.classList.add(tema);
    raiz.style.colorScheme = tema;
    try { localStorage.setItem("theme", tema); } catch { /* modo privado: solo para esta visita */ }
    sincronizar();
  }

  /** Interpolación cúbica monótona (Fritsch–Carlson) de la tabla AVANCE: suave y sin rebotes. */
  const nivelEn = (() => {
    const xs = AVANCE.map((p) => p[0]), ys = AVANCE.map((p) => p[1]), n = xs.length;
    const d = [], m = new Array(n);
    for (let i = 0; i < n - 1; i++) d.push((ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]));
    m[0] = d[0]; m[n - 1] = d[n - 2];
    for (let i = 1; i < n - 1; i++) m[i] = d[i - 1] * d[i] <= 0 ? 0 : (2 * d[i - 1] * d[i]) / (d[i - 1] + d[i]);
    return (x) => {
      if (x <= 0) return ys[0]; if (x >= 1) return ys[n - 1];
      let i = 0; while (x > xs[i + 1]) i++;
      const h = xs[i + 1] - xs[i], t = (x - xs[i]) / h, t2 = t * t, t3 = t2 * t;
      return (2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h * m[i] + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h * m[i + 1];
    };
  })();

  // ------------------------------------------------------------------ 1. campo de tinta (WebGL2)
  const VERT = `#version 300 es
  in vec2 p; void main(){ gl_Position = vec4(p, 0., 1.); }`;
  const FRAG = `#version 300 es
  precision highp float;
  uniform vec2 uRes, uVista, uToque; uniform float uR, uSemilla, uTendrils, uEscala;
  out vec4 color;
  float hash(vec2 p){ p = fract(p * vec2(123.34, 456.21) + uSemilla); p += dot(p, p + 45.32); return fract(p.x * p.y); }
  float ruido(vec2 p){ vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3. - 2. * f);
    return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y); }
  float fbm(vec2 p){ float a = .5, s = 0.; mat2 r = mat2(.8, .6, -.6, .8);
    for (int i = 0; i < 5; i++) { s += a * ruido(p); p = r * p * 2.03 + 11.7; a *= .5; } return s / .97; }
  void main(){
    vec2 px = vec2(gl_FragCoord.x, uRes.y - gl_FragCoord.y) / uRes * uVista; // px CSS, y hacia abajo
    vec2 q = (px - uToque) / uR;   // 0 en el botón, 1 en la esquina más lejana
    float d = length(q), e = uEscala;
    float lejos = smoothstep(0., .09, d);   // la gota del principio es redonda y lisa
    // dedos: el espacio se deforma dos veces (warp de warp) y el frente se rompe en lenguas
    vec2 w1 = vec2(fbm(q * 2.6 * e + vec2(1.7, 9.2)), fbm(q * 2.6 * e + vec2(8.3, 2.8))) - .5;
    vec2 w2 = vec2(fbm((q + w1 * .7) * 5.5 * e + vec2(4.1, .3)), fbm((q + w1 * .7) * 5.5 * e + vec2(.7, 6.6))) - .5;
    vec2 qw = q + (w1 * .30 + w2 * .12) * uTendrils * lejos;
    float dw = length(qw);
    float n = fbm(qw * 6. * e + 3.1) - .5;
    float f = dw + n * .22 * lejos;
    // gotas sueltas por delante del frente
    f -= smoothstep(.87, .94, ruido(q * 55. * e + 5.)) * .06 * lejos;
    // vetas: bandas finas casi paralelas al frente, estiradas y retorcidas por el flujo; su
    // contraste también cambia (hay zonas lisas y zonas muy veteadas)
    float flujo = fbm(qw * 9. * e + 7.3);
    float veta = sin(dw * 110. + flujo * 22. + n * 10.);
    veta = sign(veta) * pow(abs(veta), .6);
    float fuerza = smoothstep(.25, .75, fbm(qw * 3.4 * e + 12.)) * lejos;
    // humo: en algunas zonas, jirones alargados que llegan antes que la tinta
    float jiron = .5 + .5 * sin(dw * 30. + flujo * 26. + n * 16.); // sin «dianas»: siempre retorcido
    float zona = smoothstep(.5, .8, fbm(qw * 3.8 * e + 31.)) * lejos;
    float h = f - .075 * zona * jiron * uTendrils / 1.75;
    color = vec4(clamp((f - ${F0.toFixed(2)}) / ${FR.toFixed(2)}, 0., 1.),
                 clamp((h - ${F0.toFixed(2)}) / ${FR.toFixed(2)}, 0., 1.),
                 .5 + .5 * veta * fuerza, 1.);
  }`;

  // ------------------------------------------------------------------ 3. máscara SVG (umbral del campo)
  // <mask id="dm-tinta-mascara"> con la imagen del campo, y dentro el filtro #dm-tinta que la
  // umbraliza. La página nueva lleva mask: url(#dm-tinta-mascara) (tema.css). En cada fotograma
  // solo cambian los números de las dos feColorMatrix: es instantáneo, no se carga nada.
  // (Un filter: url(#…) puesto directamente en el pseudo-elemento ya no lo aplica Chrome 158;
  // una máscara SVG sí, y el filtro va dentro de ella, sobre la imagen.)
  let gl = null, programa = null, lienzo = null;
  function prepararGL() {
    if (gl) return true;
    lienzo = document.createElement("canvas");
    gl = lienzo.getContext("webgl2", { preserveDrawingBuffer: true, antialias: false, premultipliedAlpha: false });
    if (!gl) return false;
    const sombreador = (tipo, src) => {
      const sh = gl.createShader(tipo); gl.shaderSource(sh, src); gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh));
      return sh;
    };
    programa = gl.createProgram();
    gl.attachShader(programa, sombreador(gl.VERTEX_SHADER, VERT));
    gl.attachShader(programa, sombreador(gl.FRAGMENT_SHADER, FRAG));
    gl.bindAttribLocation(programa, 0, "p");
    gl.linkProgram(programa);
    if (!gl.getProgramParameter(programa, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(programa));
    gl.useProgram(programa);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    return true;
  }

  /** Pinta el campo para un toque en (x, y) y lo deja como imagen (PNG) en una URL blob:. */
  async function campo(x, y, ancho, alto, uR) {
    const w = Math.max(64, Math.round(ancho * RES_CAMPO)), h = Math.max(64, Math.round(alto * RES_CAMPO));
    lienzo.width = w; lienzo.height = h;
    gl.viewport(0, 0, w, h);
    gl.useProgram(programa);
    const u = (n) => gl.getUniformLocation(programa, n);
    gl.uniform2f(u("uRes"), w, h);
    gl.uniform2f(u("uVista"), ancho, alto);
    gl.uniform2f(u("uToque"), x, y);
    gl.uniform1f(u("uR"), uR);
    gl.uniform1f(u("uSemilla"), Math.random() * 10);
    gl.uniform1f(u("uTendrils"), TENDRILS);
    gl.uniform1f(u("uEscala"), ESCALA_RUIDO);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    const blob = await new Promise((ok) => lienzo.toBlob(ok, "image/png"));
    if (!blob) throw new Error("sin imagen del campo");
    return URL.createObjectURL(blob);
  }

  const SVGNS = "http://www.w3.org/2000/svg";
  let mascara = null, imagen = null, matriz = null, matrizHumo = null;
  function prepararMascara() {
    if (mascara?.isConnected) return;
    const el = (tag, attrs) => { const e = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };
    const svg = el("svg", { "aria-hidden": "true", width: "0", height: "0" });
    svg.style.cssText = "position:absolute;width:0;height:0;overflow:hidden;pointer-events:none";
    const filtro = el("filter", { id: "dm-tinta", x: "0", y: "0", width: "1", height: "1", "color-interpolation-filters": "sRGB" });
    matriz = el("feColorMatrix", { in: "SourceGraphic", type: "matrix", result: "tinta" });
    matrizHumo = el("feColorMatrix", { in: "SourceGraphic", type: "matrix", result: "humo" });
    // unión: a + HUMO·h − HUMO·a·h (en todos los canales; la máscara usa el alfa)
    const union = el("feComposite", { in: "tinta", in2: "humo", operator: "arithmetic", k1: String(-HUMO), k2: "1", k3: String(HUMO), k4: "0" });
    filtro.append(matriz, matrizHumo, union);
    mascara = el("mask", { id: "dm-tinta-mascara", maskUnits: "userSpaceOnUse", maskContentUnits: "userSpaceOnUse", x: "0", y: "0", width: "100", height: "100" });
    mascara.style.maskType = "alpha";
    imagen = el("image", { x: "0", y: "0", width: "100", height: "100", preserveAspectRatio: "none", filter: "url(#dm-tinta)" });
    mascara.append(imagen);
    const defs = el("defs", {});
    defs.append(filtro, mascara);
    svg.append(defs);
    document.body.append(svg);
  }

  /** Umbral para un nivel de tinta (en unidades de campo): alfa 0 = tema viejo, 1 = tema nuevo. */
  function fijarNivel(nivel) {
    const s = (nivel - F0) / FR; // el nivel en las unidades de R y G
    const kf = FR / FRANJA, kv = CONTRASTE_VETAS, kh = FR / SUAVIDAD_HUMO;
    matriz.setAttribute("values", `0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  ${(-kf).toFixed(3)} 0 ${kv.toFixed(3)} 0 ${(kf * s - kv * 0.5).toFixed(4)}`);
    matrizHumo.setAttribute("values", `0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 ${(-kh).toFixed(3)} 0 0 ${(kh * s).toFixed(4)}`);
  }

  /** Carga el campo en la máscara (y espera a que la imagen esté lista). */
  function cargarCampo(url, ancho, alto) {
    for (const e of [mascara, imagen]) { e.setAttribute("width", String(ancho)); e.setAttribute("height", String(alto)); }
    return new Promise((ok, mal) => {
      const t = setTimeout(() => mal(new Error("el campo no carga")), 3000);
      imagen.addEventListener("load", () => { clearTimeout(t); ok(); }, { once: true });
      imagen.addEventListener("error", () => { clearTimeout(t); mal(new Error("el campo no carga")); }, { once: true });
      imagen.setAttribute("href", url);
    });
  }

  // ------------------------------------------------------------------ cambio
  async function cambiar(boton) {
    if (enCurso) return;
    const siguiente = actual() === "dark" ? "light" : "dark";
    const quieto = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!document.startViewTransition || quieto) { aplicar(siguiente); return; }
    const ancho = innerWidth, alto = innerHeight;
    const r = boton.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    const uR = Math.hypot(Math.max(x, ancho - x), Math.max(y, alto - y));
    let url = null;
    enCurso = true;
    try {
      if (!prepararGL()) throw new Error("sin WebGL2");
      prepararMascara();
      fijarNivel(-1); // todo tema viejo hasta que empiece
      url = await campo(x, y, ancho, alto, uR);
      await cargarCampo(url, ancho, alto);
    } catch {
      if (url) URL.revokeObjectURL(url);
      enCurso = false; aplicar(siguiente); return;
    }

    raiz.classList.add("is-tema-vt");
    const vt = document.startViewTransition(() => aplicar(siguiente));
    let sosten = null, seguro = 0, cerrando = false;
    // Final: primero TODO tema nuevo (máscara entera), un fotograma así, y luego se acaba la
    // transición. La clase is-tema-vt (máscara + sin fundido) se quita solo cuando ya no hay
    // capturas: si se quita antes, el navegador mete su fundido por defecto y se ve un destello.
    const cerrar = () => {
      if (cerrando) return;
      cerrando = true;
      clearTimeout(seguro);
      fijarNivel(99);
      requestAnimationFrame(() => (sosten ? sosten.finish() : vt.skipTransition()));
    };
    vt.finished.finally(() => {
      clearTimeout(seguro);
      raiz.classList.remove("is-tema-vt");
      enCurso = false;
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    vt.ready.then(() => {
      // la transición dura lo que esta animación «vacía»; el avance lo lleva el bucle de abajo
      sosten = raiz.animate({ opacity: [1, 1] }, { duration: DURACION * 20, pseudoElement: "::view-transition-new(root)" });
      seguro = setTimeout(cerrar, DURACION + 3000);
      const t0 = performance.now();
      const paso = () => {
        if (cerrando) return;
        const x01 = Math.min(1, (performance.now() - t0) / DURACION);
        if (x01 >= 1) { cerrar(); return; }
        fijarNivel(nivelEn(x01));
        requestAnimationFrame(paso);
      };
      paso();
    }).catch(cerrar);
  }

  // Los botones los pinta React (y cambian al navegar): delegación en el documento.
  document.addEventListener("click", (e) => {
    const b = e.target.closest?.("[data-tema]");
    if (b) { e.preventDefault(); cambiar(b); }
  });
  // estado accesible al día cuando alguien llega al botón (y el WebGL listo antes del clic)
  document.addEventListener("focusin", (e) => { if (e.target.closest?.("[data-tema]")) sincronizar(); });
  document.addEventListener("pointerover", (e) => {
    if (!e.target.closest?.("[data-tema]")) return;
    sincronizar();
    try { prepararGL(); } catch { /* sin WebGL2: cambio instantáneo */ }
  });
})();
