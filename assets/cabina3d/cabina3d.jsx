// Sección «mundos» de la portada: cabina de nave en WebGL (three.js), envuelta como componente React
// y registrada en Reflex desde demeter/components/cabina3d.py.
//
//  · Pared: la cara interior de un cilindro (radio R) con un hueco squircle por ventana. Pared, marcos
//    con doble borde y bisel son UNA malla con una textura (alpha en los huecos), así giran juntos.
//  · Mundos: detrás de cada hueco, MUCHO más lejos que la pared (paisaje a 3R, montes a 2R, primer
//    plano a 1.4R). Cada mundo solo se ve por SU hueco (stencil). El parallax sale solo de la
//    profundidad: el ojo va EJE unidades detrás del eje de giro, así que al girar se desplaza y el
//    paisaje lejano se mueve bastante menos que el marco (se ven otras partes de él por el hueco).
//  · Lo que gira es la CÁMARA (pivot.rotation.y). Paso = 360° / N huecos. Los mundos van del primero
//    al último (sin bucle); los huecos que sobran del anillo muestran solo cielo.
//  · Rueda: cambia de mundo; en el primero (hacia arriba) y el último (hacia abajo) deja que la página
//    siga con su scroll normal.
//  · Postprocesado: un EffectComposer con un ShaderPass final (Bayer 4×4, posterizado, grano, viñeta).
//  · Títulos, subtítulos y «Explorar» son DOM, colocados cada frame sobre la proyección de su hueco.
//  · Sin WebGL o con prefers-reduced-motion se usa la versión CSS (assets/proto/cabina/main.js).
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

// ---------------------------------------------------------------- ajustes
const N_HUECOS = 6; // huecos en el anillo (60° cada uno); los mundos ocupan los primeros
const R = 6; // radio de la pared
const EJE = 3; // el ojo va este tanto detrás del eje de giro: al girar se desplaza y hay parallax real
const A = (25 * Math.PI) / 180; // semiancho angular del cristal (medido desde el eje)
const R_CIELO = 3 * R, R_MONTES = 2 * R, R_CERCA = 1.4 * R, R_ESTRELLAS = 2.5 * R;
const N_SUPER = 5; // exponente del squircle
const DURACION = 1300; // ms
const COOLDOWN_RUEDA = 400; // ms sin capturar la rueda tras soltarla en un extremo
const RESISTENCIA = 0.35;
const UMBRAL_RUEDA = 55;
const LOOK = (2 * Math.PI) / 180; // mouse-look ±2°
const PIXEL_RATIO_MAX = 1.5;
const COLORES = { pared: "#14493b", paredHi: "#1f6a55", paredLo: "#07261f", marco1: "#eef6e4", marco2: "#cfe3cf", marco3: "#b9d3bd", oscuro: "#07261f", anillo: "#2f7a62" };

// ---------------------------------------------------------------- utilidades
const mod = (n, m) => ((n % m) + m) % m;
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
function bezier(x1, y1, x2, y2) {
  // cubic-bezier(x1,y1,x2,y2) como función t → y (Newton sobre x)
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const sx = (t) => ((ax * t + bx) * t + cx) * t;
  const sy = (t) => ((ay * t + by) * t + cy) * t;
  const dx = (t) => (3 * ax * t + 2 * bx) * t + cx;
  return (x) => {
    let t = x;
    for (let i = 0; i < 8; i++) { const e = sx(t) - x; const d = dx(t); if (Math.abs(e) < 1e-5 || !d) break; t -= e / d; }
    return sy(clamp(t));
  };
}
const EASE = bezier(0.16, 1, 0.3, 1); // de salida: arranca ya y frena
/** Curva de salida que empieza con la pendiente `s0` (velocidad del gesto, en «recorrido por duración»). */
function easeConVelocidad(s0) {
  if (!(s0 > 0)) return EASE;
  let x1 = 0.16, y1 = s0 * x1;
  if (y1 > 1) { y1 = 1; x1 = Math.max(0.02, 1 / s0); }
  return bezier(x1, y1, 0.3, 1);
}
const easeOut = (t) => 1 - Math.pow(1 - t, 2);
const easeInOut = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);

function hayWebGL() {
  try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch { return false; }
}

/** Contorno squircle (superelipse) unitario: puntos [u, v] en [-1, 1]. */
function squircle(pasos = 160) {
  const pts = [];
  for (let k = 0; k < pasos; k++) {
    const t = (k / pasos) * Math.PI * 2, c = Math.cos(t), s = Math.sin(t);
    pts.push([Math.sign(c) * Math.pow(Math.abs(c), 2 / N_SUPER), Math.sign(s) * Math.pow(Math.abs(s), 2 / N_SUPER)]);
  }
  return pts;
}
const SQUIRCLE = squircle();

// ---------------------------------------------------------------- geometría según el tamaño de pantalla
function medirLayout(ancho, alto) {
  const aspecto = ancho / alto;
  const D0 = R + EJE; // profundidad ojo → centro del hueco
  const tanH = (R * Math.sin(A)) / (R * Math.cos(A) + EJE); // semiancho del hueco visto desde el ojo
  const apaisado = aspecto >= 1.15;
  // En horizontal el fov es 45°; en vertical se abre lo justo para que el cristal ocupe ~86 % del ancho.
  const fov = apaisado ? 45 : clamp((2 * Math.atan(tanH / 0.86 / aspecto) * 180) / Math.PI, 45, 84);
  const tanV = Math.tan(((fov / 2) * Math.PI) / 180);
  const fraccionAlto = apaisado ? 0.58 : 0.55; // alto del cristal en fracción del alto de pantalla
  const yNdc = apaisado ? 0.2 : 0.12; // el cristal queda por encima de la consola
  const H = fraccionAlto * tanV * D0;
  const yc = yNdc * tanV * D0;
  const tanVmax = Math.tan((((fov + 3) / 2 + 2) * Math.PI) / 180);
  const alturaCil = 2 * (tanVmax * (R + EJE + 1) + 1);
  return { aspecto, fov, H, yc, tanH, D0, alturaCil, movil: ancho <= 760 };
}

// ---------------------------------------------------------------- textura de la pared (un segmento, se repite N veces)
function texturaPared(L, N) {
  const arco = R * ((2 * Math.PI) / N); // arco de un segmento
  // píxeles por unidad, iguales en horizontal y vertical; el canvas no pasa de 4096 px de alto
  const W = Math.round(Math.min(1536, (4096 * arco) / L.alturaCil)), ppu = W / arco;
  const Hpx = Math.round(L.alturaCil * ppu);
  const c = document.createElement("canvas"); c.width = W; c.height = Hpx;
  const g = c.getContext("2d");
  const cx = W / 2, cy = (L.alturaCil / 2 - L.yc) * ppu;
  const a = R * A * ppu, b = L.H * ppu;

  // pared: halo más claro alrededor de cada ventana, juntas de panel
  const fondo = g.createRadialGradient(cx, cy, a * 0.2, cx, cy, Math.max(W, Hpx) * 0.75);
  fondo.addColorStop(0, COLORES.paredHi); fondo.addColorStop(0.45, COLORES.pared); fondo.addColorStop(1, COLORES.paredLo);
  g.fillStyle = fondo; g.fillRect(0, 0, W, Hpx);
  g.fillStyle = "rgba(0,0,0,.28)"; g.fillRect(0, 0, 3, Hpx); g.fillRect(W - 3, 0, 3, Hpx);
  g.fillStyle = "rgba(255,255,255,.06)"; g.fillRect(0, cy - b - a * 0.32, W, 2);
  g.fillStyle = "rgba(0,0,0,.22)"; g.fillRect(0, cy + b + a * 0.3, W, 3);

  const ruta = (da, db) => {
    const p = new Path2D();
    SQUIRCLE.forEach(([u, v], i) => (i ? p.lineTo : p.moveTo).call(p, cx + u * (a + da), cy - v * (b + db)));
    p.closePath();
    return p;
  };
  const f = a * 0.075, anillo = a * 0.028, linea = Math.max(3, a * 0.011);

  // marco: sombra, contorno exterior oscuro, anillo, bisel claro y contorno interior oscuro
  g.save(); g.shadowColor = "rgba(0,0,0,.4)"; g.shadowBlur = a * 0.12; g.shadowOffsetY = a * 0.05;
  g.fillStyle = COLORES.oscuro; g.fill(ruta(f + anillo + linea * 2, f + anillo + linea * 2)); g.restore();
  g.fillStyle = COLORES.anillo; g.fill(ruta(f + anillo + linea, f + anillo + linea));
  g.fillStyle = COLORES.oscuro; g.fill(ruta(f + linea, f + linea));
  const bisel = g.createLinearGradient(cx - a, cy - b, cx + a, cy + b);
  bisel.addColorStop(0, COLORES.marco1); bisel.addColorStop(0.6, COLORES.marco2); bisel.addColorStop(1, COLORES.marco3);
  g.fillStyle = bisel; g.fill(ruta(f, f));
  g.strokeStyle = "rgba(255,255,255,.55)"; g.lineWidth = linea * 0.6; g.stroke(ruta(f * 0.82, f * 0.82));

  // el hueco: transparente
  const cristal = ruta(0, 0);
  g.globalCompositeOperation = "destination-out"; g.fill(cristal); g.globalCompositeOperation = "source-over";
  // bisel interior: sombra que cae dentro del cristal (semitransparente: deja ver el mundo)
  g.save(); g.clip(cristal);
  g.shadowColor = "rgba(0,0,0,.55)"; g.shadowBlur = a * 0.14; g.shadowOffsetY = a * 0.035;
  const marcoHueco = new Path2D(); marcoHueco.rect(-W, -Hpx, W * 3, Hpx * 3); marcoHueco.addPath(cristal);
  g.fillStyle = "#000"; g.fill(marcoHueco, "evenodd"); g.restore();
  g.strokeStyle = COLORES.oscuro; g.lineWidth = linea * 1.4; g.stroke(cristal);

  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = THREE.RepeatWrapping;
  t.repeat.set(N, 1);
  t.offset.x = 0.5; // centra un hueco en cada paso
  t.anisotropy = 8;
  return t;
}

// ---------------------------------------------------------------- texturas de las capas de cada mundo
function texturaCanvas(w, h, pintar) {
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  pintar(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
const RIDGE_LEJOS = new Path2D("M0 600V430L160 360L320 410L520 290L720 400L900 330L1100 410L1300 340L1480 400L1600 370V600Z");
const RIDGE_CERCA = new Path2D("M0 600V500C200 440 300 520 520 478S900 420 1100 488S1450 455 1600 500V600Z");
function texturaMontana(path, color, alpha, alto) {
  return texturaCanvas(1600, 600, (g, w, h) => {
    g.save(); g.translate(0, h * (1 - alto)); g.scale(1, alto); g.globalAlpha = alpha; g.fillStyle = color; g.fill(path); g.restore();
  });
}
function texturaSombra(velo) {
  return texturaCanvas(512, 512, (g, w, h) => {
    const v = g.createLinearGradient(0, 0, 0, h);
    v.addColorStop(0, "rgba(5,25,20,.42)"); v.addColorStop(0.42, "rgba(5,25,20,.05)"); v.addColorStop(1, "rgba(5,25,20,.5)");
    g.fillStyle = v; g.fillRect(0, 0, w, h);
    if (velo) { // oscurece el centro para que el título se lea sobre fotos con mucho detalle
      const r = g.createRadialGradient(w / 2, h * 0.47, 0, w / 2, h * 0.47, w * 0.42);
      r.addColorStop(0, `rgba(4,20,16,${Math.min(0.95, 1.4 * velo)})`); r.addColorStop(0.6, `rgba(4,20,16,${0.8 * velo})`); r.addColorStop(1, "rgba(4,20,16,0)");
      g.fillStyle = r; g.fillRect(0, 0, w, h);
    }
  });
}
let BORDE_SUAVE = null;
function texturaBordeSuave() {
  if (BORDE_SUAVE) return BORDE_SUAVE;
  const c = document.createElement("canvas"); c.width = c.height = 256;
  const g = c.getContext("2d");
  g.fillStyle = "#000"; g.fillRect(0, 0, 256, 256);
  g.filter = "blur(18px)"; g.fillStyle = "#fff"; g.fillRect(34, 34, 188, 188);
  BORDE_SUAVE = new THREE.CanvasTexture(c);
  return BORDE_SUAVE;
}

// ---------------------------------------------------------------- shaders
const DITHER = {
  uniforms: { tDiffuse: { value: null }, uTime: { value: 0 }, uLevels: { value: 7 }, uPixel: { value: 2 } },
  vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
  fragmentShader: `
    uniform sampler2D tDiffuse; uniform float uTime, uLevels, uPixel; varying vec2 vUv;
    float bayer2(vec2 a){ a = floor(a); return fract(a.x / 2.0 + a.y * a.y * 0.75); }
    float bayer4(vec2 a){ return bayer2(0.5 * a) * 0.25 + bayer2(a); }
    float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
    void main(){
      vec3 c = texture2D(tDiffuse, vUv).rgb;
      float vig = smoothstep(0.95, 0.3, length((vUv - 0.5) * vec2(1.1, 1.25)));
      c *= mix(0.76, 1.0, vig);                                                  // viñeta suave
      c += (hash(gl_FragCoord.xy + floor(uTime * 14.0)) - 0.5) * 0.04;          // grano temporal (14 fps)
      float d = bayer4(floor(gl_FragCoord.xy / uPixel)) - 0.5;                   // Bayer 4×4, celda uPixel
      float L = uLevels - 1.0;
      c = floor(c * L + 0.5 + d) / L;                                            // posterizado
      gl_FragColor = vec4(clamp(c, 0.0, 1.0), 1.0);
    }`,
};
const ESTRELLAS_VERT = `
  attribute float aFase; uniform float uTime, uPix; varying float vA;
  void main(){
    vec3 p = position; p.y += sin(uTime * 0.4 + aFase * 6.2831) * 0.04;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
    float tw = 0.5 + 0.5 * sin(uTime * 1.3 + aFase * 6.2831);
    vA = 0.15 + 0.8 * tw; gl_PointSize = (1.6 + 2.6 * tw) * uPix;
  }`;
const ESTRELLAS_FRAG = `
  uniform vec3 uColor; varying float vA;
  void main(){ float d = length(gl_PointCoord - 0.5); if (d > 0.5) discard; gl_FragColor = vec4(uColor, vA * smoothstep(0.5, 0.15, d)); }`;

// ---------------------------------------------------------------- la escena
function iniciarEscena(raiz, mundos) {
  const M = mundos.length, N = Math.max(N_HUECOS, M), PASO = (2 * Math.PI) / N;
  const $ = (s) => raiz.querySelector(s);
  const lienzoCaja = $("[data-gl]"), rotulosCaja = $("[data-rotulos]"), escena3 = $("[data-escena]");
  const consolaVista = $("[data-consola-vista]"), puntosEl = $("[data-puntos]"), lectura = $("[data-lectura]"), anuncio = $("[data-anuncio]");

  // ---- renderer + postprocesado
  const renderer = new THREE.WebGLRenderer({ antialias: true, stencil: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, PIXEL_RATIO_MAX));
  lienzoCaja.appendChild(renderer.domElement);
  renderer.domElement.setAttribute("aria-hidden", "true");
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(COLORES.paredLo);
  const pivot = new THREE.Object3D(); // gira la cámara
  scene.add(pivot);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.05, 100);
  camera.position.set(0, 0, EJE);
  pivot.add(camera);

  const rt = new THREE.WebGLRenderTarget(2, 2, { type: THREE.HalfFloatType, stencilBuffer: true });
  const composer = new EffectComposer(renderer, rt);
  composer.addPass(new RenderPass(scene, camera));
  composer.addPass(new OutputPass());
  const dither = new ShaderPass(DITHER);
  composer.addPass(dither);

  // ---- fotos (se cargan una vez por mundo y las comparten sus copias)
  const cargador = new THREE.TextureLoader();
  const fotos = mundos.map((m) => {
    const info = { tex: null, cielo: new THREE.Color(m.colores?.lejos || "#7aa0b0") };
    info.tex = cargador.load(m.img, (t) => {
      // color medio de la franja de arriba: el fondo que se ve si miras muy de lado por el hueco
      try {
        const c = document.createElement("canvas"); c.width = 16; c.height = 4;
        const g = c.getContext("2d"); g.drawImage(t.image, 0, 0, t.image.width, t.image.height * 0.3, 0, 0, 16, 4);
        const d = g.getImageData(0, 0, 16, 4).data; let r = 0, gg = 0, b = 0;
        for (let i = 0; i < d.length; i += 4) { r += d[i]; gg += d[i + 1]; b += d[i + 2]; }
        const n = d.length / 4; info.cielo.setRGB(r / n / 255, gg / n / 255, b / n / 255, THREE.SRGBColorSpace);
      } catch { /* sin acceso a los píxeles: se queda el color de la montaña */ }
      ajustarFotos();
    });
    info.tex.colorSpace = THREE.SRGBColorSpace;
    info.tex.anisotropy = 8;
    return info;
  });

  // ---- construcción (se rehace al cambiar mucho el tamaño de la pantalla)
  let L = null, pared = null, huecos = [];
  const desechables = [];
  const guardar = (o) => { desechables.push(o); return o; };

  function plano(r, L, margenH = 1.15, oblicuo = 0.5) {
    const Dr = r + EJE;
    const wr = Dr * L.tanH * margenH + (r - R) * oblicuo;
    const arriba = (Dr * (L.yc + L.H)) / L.D0 + (r - R) * 0.25 + 0.15;
    const abajo = (Dr * (L.yc - L.H)) / L.D0 - (r - R) * 0.25 - 0.15;
    return { w: wr * 2, h: arriba - abajo, y: (arriba + abajo) / 2, z: -r };
  }
  function stencil(mat, ref) {
    Object.assign(mat, { stencilWrite: true, stencilRef: ref, stencilFunc: THREE.EqualStencilFunc, stencilZPass: THREE.KeepStencilOp, stencilFail: THREE.KeepStencilOp, stencilZFail: THREE.KeepStencilOp, depthTest: false, depthWrite: false });
    return mat;
  }
  function malla(geo, mat, orden, d) {
    const m = new THREE.Mesh(guardar(geo), guardar(mat));
    m.renderOrder = orden; m.position.set(0, d.y, d.z);
    return m;
  }

  function construir() {
    // limpia lo anterior
    if (pared) scene.remove(pared);
    huecos.forEach((h) => scene.remove(h.grupo));
    desechables.splice(0).forEach((o) => o.dispose?.());
    huecos = [];

    // pared: cilindro visto por dentro, con la textura de huecos repetida N veces
    const texPared = guardar(texturaPared(L, N));
    pared = new THREE.Mesh(
      guardar(new THREE.CylinderGeometry(R, R, L.alturaCil, 256, 1, true)),
      guardar(new THREE.MeshBasicMaterial({ map: texPared, side: THREE.BackSide, transparent: true, depthTest: false, depthWrite: false })),
    );
    pared.renderOrder = 10;
    scene.add(pared);

    // geometría del hueco (máscara de stencil): abanico sobre la superficie curva del cilindro
    const Rm = R - 0.002;
    const pos = [0, L.yc, -Rm];
    SQUIRCLE.forEach(([u, v]) => { const al = u * A; pos.push(Rm * Math.sin(al), L.yc + v * L.H, -Rm * Math.cos(al)); });
    const idx = []; for (let k = 1; k <= SQUIRCLE.length; k++) idx.push(0, k, (k % SQUIRCLE.length) + 1);
    const geoHueco = guardar(new THREE.BufferGeometry());
    geoHueco.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    geoHueco.setIndex(idx);

    const dFondo = { w: 140, h: 90, y: L.yc, z: -(R_CIELO + 3) };
    const dFoto = plano(R_CIELO, L), dLejos = plano(R_MONTES, L), dCerca = plano(R_CERCA, L), dEstrellas = plano(R_ESTRELLAS, L), dSombra = plano(R + 0.25, L, 1.05, 0.2);
    const sombras = mundos.map((m) => guardar(texturaSombra(m.velo || 0)));
    const montes = mundos.map((m) => [guardar(texturaMontana(RIDGE_LEJOS, m.colores.lejos, 0.45, 0.46)), guardar(texturaMontana(RIDGE_CERCA, m.colores.cerca, 0.75, 0.3))]);

    for (let i = 0; i < N; i++) {
      const w = i < M ? i : -1, m = w >= 0 ? mundos[w] : null, ref = i + 1;
      const grupo = new THREE.Group();
      grupo.rotation.y = -i * PASO; // hueco i centrado cuando pivot.rotation.y = -i·PASO

      const mascara = new THREE.Mesh(geoHueco, guardar(new THREE.MeshBasicMaterial({
        colorWrite: false, depthWrite: false, depthTest: false,
        stencilWrite: true, stencilRef: ref, stencilFunc: THREE.AlwaysStencilFunc, stencilZPass: THREE.ReplaceStencilOp,
      })));
      mascara.renderOrder = 0;
      grupo.add(mascara);

      const fondo = malla(new THREE.PlaneGeometry(dFondo.w, dFondo.h), stencil(new THREE.MeshBasicMaterial({ color: m ? fotos[w].cielo : new THREE.Color("#0d3a33") }), ref), 1, dFondo);
      const capas = [fondo];
      let foto = null;
      if (m) {
        foto = malla(new THREE.PlaneGeometry(dFoto.w, dFoto.h), stencil(new THREE.MeshBasicMaterial({ map: fotos[w].tex, alphaMap: texturaBordeSuave(), transparent: true }), ref), 2, dFoto);
        const lejos = malla(new THREE.PlaneGeometry(dLejos.w, dLejos.h), stencil(new THREE.MeshBasicMaterial({ map: montes[w][0], transparent: true }), ref), 4, dLejos);
        const cerca = malla(new THREE.PlaneGeometry(dCerca.w, dCerca.h), stencil(new THREE.MeshBasicMaterial({ map: montes[w][1], transparent: true }), ref), 5, dCerca);
        const sombra = malla(new THREE.PlaneGeometry(dSombra.w, dSombra.h), stencil(new THREE.MeshBasicMaterial({ map: sombras[w], transparent: true }), ref), 6, dSombra);
        foto.userData.plano = dFoto;
        capas.push(foto, lejos, cerca, sombra);
      }

      // estrellas / polvo: parpadean y flotan (shader)
      const n = 34, pts = new Float32Array(n * 3), fases = new Float32Array(n);
      let semilla = 97 + i * 31; const azar = () => ((semilla = (semilla * 16807) % 2147483647) - 1) / 2147483646;
      for (let k = 0; k < n; k++) {
        pts[k * 3] = (azar() - 0.5) * dEstrellas.w * 0.8;
        pts[k * 3 + 1] = dEstrellas.y + (azar() * 0.9 - 0.05) * dEstrellas.h * 0.5;
        pts[k * 3 + 2] = dEstrellas.z; fases[k] = azar();
      }
      const geoE = guardar(new THREE.BufferGeometry());
      geoE.setAttribute("position", new THREE.BufferAttribute(pts, 3));
      geoE.setAttribute("aFase", new THREE.BufferAttribute(fases, 1));
      const matE = guardar(stencil(new THREE.ShaderMaterial({
        uniforms: { uTime: { value: 0 }, uPix: { value: renderer.getPixelRatio() }, uColor: { value: new THREE.Color(m?.colores.particula || "#ffffff") } },
        vertexShader: ESTRELLAS_VERT, fragmentShader: ESTRELLAS_FRAG, transparent: true,
      }), ref));
      const estrellas = new THREE.Points(geoE, matE); estrellas.renderOrder = 3;

      grupo.add(...capas, estrellas);
      scene.add(grupo);

      // puntos de referencia para colocar el DOM encima del hueco
      const ref3 = {
        izq: new THREE.Vector3(-R * Math.sin(A), L.yc, -R * Math.cos(A)), der: new THREE.Vector3(R * Math.sin(A), L.yc, -R * Math.cos(A)),
        arr: new THREE.Vector3(0, L.yc + L.H, -R), aba: new THREE.Vector3(0, L.yc - L.H, -R), cen: new THREE.Vector3(0, L.yc, -R),
      };
      huecos.push({ grupo, mundo: w, foto, matE, ref3 });
    }
    ajustarFotos();
  }

  // recorte «cover» de cada foto según el tamaño de su plano
  function ajustarFotos() {
    huecos.forEach((h) => {
      if (h.mundo < 0) return;
      const t = fotos[h.mundo].tex, img = t.image, d = h.foto.userData.plano;
      h.grupo.children[1].material.color = fotos[h.mundo].cielo;
      if (!img || !img.width || !d) return;
      const pa = d.w / d.h, ia = img.width / img.height;
      if (pa > ia) { t.repeat.set(1, ia / pa); t.offset.set(0, (1 - ia / pa) / 2); }
      else { t.repeat.set(pa / ia, 1); t.offset.set((1 - pa / ia) / 2, 0); }
    });
  }

  // ---- rótulos DOM (título, subtítulo, «Explorar»), uno por hueco
  const rotulos = Array.from({ length: M }, (_, i) => {
    const m = mundos[i];
    const r = document.createElement("div");
    r.className = "rotulo"; r.setAttribute("aria-hidden", "true");
    r.innerHTML = `<div class="win__text"><h3 class="win__title"></h3><p class="win__sub"></p></div><button type="button" class="win__cta" tabindex="-1">Explorar</button>`;
    r.querySelector(".win__title").textContent = m.titulo;
    r.querySelector(".win__sub").textContent = m.sub;
    r.querySelector(".win__cta").addEventListener("click", () => abrirDetalle(m));
    rotulosCaja.appendChild(r);
    return r;
  });

  // ---- puntos de paginación
  puntosEl.replaceChildren(...mundos.map((m, w) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "hud__dot"; b.setAttribute("aria-label", `Ir a ${m.titulo}`);
    b.addEventListener("click", () => irAMundo(w));
    return b;
  }));
  const puntos = [...puntosEl.children];

  // ---- estado
  const st = { pos: 0, anim: null, arrastre: null, look: { x: 0, y: 0, tx: 0, ty: 0 }, activo: -1, ancho: 1, alto: 1, proyecciones: [] };
  const v3 = new THREE.Vector3();
  const flechas = [...raiz.querySelectorAll("[data-paso]")];
  const ULTIMO = M - 1;
  const limitar = (p) => clamp(p, 0, ULTIMO);

  function fijarActivo(w) {
    if (w === st.activo) return;
    st.activo = w;
    const m = mundos[w];
    rotulos.forEach((r, i) => {
      const on = i === w;
      r.setAttribute("aria-hidden", on ? "false" : "true");
      r.querySelector(".win__cta").tabIndex = on ? 0 : -1;
      r.classList.toggle("is-active", on);
      if (on) [".win__title", ".win__sub", ".win__cta"].forEach((sel, k) => {
        r.querySelector(sel).animate([{ transform: "translateY(20px)", opacity: 0 }, { transform: "none", opacity: 1 }],
          { duration: 700, delay: 350 + k * 60, easing: "cubic-bezier(.23,1,.32,1)", fill: "backwards" });
      });
    });
    puntos.forEach((p, k) => { p.classList.toggle("is-on", k === w); p.setAttribute("aria-current", k === w ? "true" : "false"); });
    // en los extremos, la flecha hacia fuera queda desactivada
    flechas.forEach((b) => { const d = Number(b.dataset.paso); b.disabled = (d < 0 && w === 0) || (d > 0 && w === ULTIMO); });
    lectura.textContent = m.lectura || "";
    lectura.animate([{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }], { duration: 600, delay: 300, easing: "cubic-bezier(.23,1,.32,1)", fill: "backwards" });
    anuncio.textContent = `${m.titulo}. ${m.sub}`;
  }

  // ---- navegación (del primero al último). `v0`: velocidad del gesto en posiciones/ms (rueda o arrastre)
  function irA(destino, v0 = 0) {
    if (raiz.classList.contains("is-detalle")) return;
    destino = limitar(Math.round(destino));
    const recorrido = destino - st.pos;
    // el giro hereda la velocidad del gesto: arranca con ella (si va hacia el destino) y frena
    const s0 = Math.abs(recorrido) > 1e-3 && Math.sign(v0) === Math.sign(recorrido) ? (Math.abs(v0) * DURACION) / Math.abs(recorrido) : 0;
    st.anim = { desde: st.pos, hasta: destino, t0: performance.now(), ease: easeConVelocidad(s0) };
    fijarActivo(destino);
    despertar();
  }
  const destinoActual = () => (st.anim ? st.anim.hasta : Math.round(st.pos));
  const paso = (d, v0) => { const a = destinoActual(), b = limitar(a + d); if (b !== a) irA(b, v0); return b !== a; };
  const irAMundo = (w) => { if (w !== destinoActual()) irA(w); };

  // ---- rueda / trackpad
  //  · en medio: cambia de mundo (acumulador con umbral; bloqueo mientras gira; la inercia no cuenta)
  //  · en el último hacia abajo / el primero hacia arriba: NO se hace preventDefault y la página sigue su
  //    scroll; después, COOLDOWN_RUEDA ms sin capturar la rueda para que no «rebote»
  let acc = 0, ultimoEvento = 0, ultimoAbs = 0, libreHasta = 0, idRueda = 0, sueltaHasta = 0, estabaEnVista = false;
  const enVista = () => { const r = raiz.getBoundingClientRect(); return Math.abs(r.top) < innerHeight * 0.12 && r.bottom > innerHeight * 0.88; };
  // al entrar en la sección, la inercia del gesto que te ha traído no cambia de mundo durante COOLDOWN_RUEDA ms
  function alScroll() {
    const vista = enVista();
    if (vista && !estabaEnVista) libreHasta = Math.max(libreHasta, performance.now() + COOLDOWN_RUEDA);
    estabaEnVista = vista;
  }
  function alRueda(e) {
    const ahora = performance.now();
    if (!enVista() || raiz.classList.contains("is-detalle") || ahora < sueltaHasta) return;
    const delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY, abs = Math.abs(delta);
    const nuevo = ahora - ultimoEvento > 140 || abs > ultimoAbs * 1.15;
    const dt = Math.max(8, ahora - ultimoEvento);
    ultimoEvento = ahora; ultimoAbs = abs;
    const destino = destinoActual();
    const haciaFuera = (delta > 0 && destino >= ULTIMO) || (delta < 0 && destino <= 0);
    const girando = !!st.anim || ahora < libreHasta;
    // extremo + gesto NUEVO hacia fuera con todo quieto: la página hace su scroll normal
    if (haciaFuera && !girando && nuevo && acc === 0) { sueltaHasta = ahora + COOLDOWN_RUEDA; return; }
    e.preventDefault();
    if (girando || haciaFuera) return; // durante el giro, o cola de inercia en un extremo: se absorbe
    if (ahora - idRueda > 180) acc = 0;
    if (acc === 0 && !nuevo) return;
    idRueda = ahora; acc += delta;
    if (Math.abs(acc) >= UMBRAL_RUEDA) {
      const d = Math.sign(acc); acc = 0;
      libreHasta = ahora + DURACION * 0.85;
      // la velocidad de la rueda, en la misma escala que el arrastre (px → posiciones)
      const v0 = d * Math.min((abs / dt) * (RESISTENCIA / (st.ancho * 0.15)), 0.004);
      paso(d, v0);
    }
  }

  // ---- arrastre: sigue al dedo en tiempo real; en los extremos, rebote elástico (rubber band)
  function alBajar(e) {
    if (e.button > 0 || e.target.closest("button, a, .cab3__console, .cab3__detail")) return;
    st.arrastre = { x0: e.clientX, y0: e.clientY, base: st.pos, movido: false, eje: null, id: e.pointerId, muestras: [[performance.now(), e.clientX]] };
  }
  function alMover(e) {
    const r = raiz.getBoundingClientRect();
    st.look.tx = ((e.clientX - r.left) / r.width) * 2 - 1;
    st.look.ty = ((e.clientY - r.top) / r.height) * 2 - 1;
    const a = st.arrastre;
    if (!a || e.pointerId !== a.id) return;
    const dx = e.clientX - a.x0, dy = e.clientY - a.y0;
    if (!a.eje && Math.hypot(dx, dy) > 6) {
      a.eje = Math.abs(dx) > Math.abs(dy) ? "x" : "y";
      if (a.eje === "y") { st.arrastre = null; return; } // vertical: deja hacer scroll a la página
      a.movido = true; st.anim = null; a.base = st.pos;
      raiz.setPointerCapture?.(e.pointerId);
    }
    if (a.eje !== "x") return;
    const libre = a.base - (dx * RESISTENCIA) / (st.ancho * 0.15);
    st.pos = libre < 0 ? libre / 3 : libre > ULTIMO ? ULTIMO + (libre - ULTIMO) / 3 : libre; // rubber band
    a.muestras.push([performance.now(), e.clientX]); if (a.muestras.length > 6) a.muestras.shift();
    despertar();
  }
  function alSoltar(e) {
    const a = st.arrastre; st.arrastre = null;
    if (!a || e.pointerId !== a.id) return;
    if (!a.movido) { clicLateral(e.clientX); return; }
    const dx = e.clientX - a.x0;
    const [t0, x0] = a.muestras[0], [t1, x1] = a.muestras[a.muestras.length - 1];
    const v = t1 > t0 ? (x1 - x0) / (t1 - t0) : 0; // px/ms
    const v0 = (-v * RESISTENCIA) / (st.ancho * 0.15); // en posiciones/ms
    const origen = Math.round(a.base);
    if (Math.abs(dx) > 70 || Math.abs(v) > 0.6) irA(origen + (dx < 0 || v < -0.6 ? 1 : -1), v0);
    else irA(origen, v0); // vuelve a la ventana actual (o rebota desde el extremo)
  }
  function clicLateral(x) {
    const act = st.proyecciones[st.activo];
    if (!act) return;
    if (x > act.der + 8) paso(1); else if (x < act.izq - 8) paso(-1);
  }

  function alTeclado(e) {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    if (raiz.classList.contains("is-detalle")) { if (e.key === "Escape") cerrarDetalle(); return; }
    if (!enVista() && !raiz.contains(document.activeElement)) return;
    if (e.key === "ArrowRight") { e.preventDefault(); paso(1); }
    if (e.key === "ArrowLeft") { e.preventDefault(); paso(-1); }
    // ↓ / Av Pág siguen por la portada y ↑ / Re Pág suben (la rueda gira la cabina sin fin)
    if (["ArrowDown", "PageDown"].includes(e.key)) { e.preventDefault(); document.getElementById("gemelo")?.scrollIntoView({ behavior: "smooth" }); }
    if (["ArrowUp", "PageUp"].includes(e.key)) { e.preventDefault(); scrollTo({ top: raiz.offsetTop - innerHeight, behavior: "smooth" }); }
  }
  const alFlecha = (e) => paso(Number(e.currentTarget.dataset.paso));

  // ---- detalle («Explorar»): las animaciones están en CSS (.cab3.is-detalle)
  const detalle = $("[data-detalle]");
  let ultimoFoco = null;
  function abrirDetalle(m) {
    ultimoFoco = document.activeElement;
    const img = detalle.querySelector("[data-d-img]");
    img.src = m.img; img.alt = m.alt;
    detalle.querySelector("[data-d-pregunta]").textContent = m.pregunta;
    detalle.querySelector("[data-d-texto]").textContent = m.texto;
    const ver = detalle.querySelector("[data-d-ver]"); ver.href = m.href; ver.textContent = "Ver proyecto";
    raiz.classList.add("is-detalle");
    escena3.setAttribute("inert", "");
    setTimeout(() => ver.focus({ preventScroll: true }), 1200);
  }
  function cerrarDetalle() {
    raiz.classList.remove("is-detalle");
    escena3.removeAttribute("inert");
    ultimoFoco?.focus?.({ preventScroll: true });
  }
  const volver = detalle.querySelector("[data-d-volver]");
  volver.addEventListener("click", cerrarDetalle);

  // ---- tamaño
  function redimensionar() {
    const w = Math.max(1, raiz.clientWidth), h = Math.max(1, raiz.clientHeight);
    st.ancho = w; st.alto = h;
    renderer.setSize(w, h, false);
    composer.setSize(w, h);
    camera.aspect = w / h;
    const nuevo = medirLayout(w, h);
    const cambia = !L || Math.abs(nuevo.H - L.H) > 0.05 || Math.abs(nuevo.yc - L.yc) > 0.05 || Math.abs(nuevo.alturaCil - L.alturaCil) > 0.3;
    L = nuevo;
    if (cambia) construir();
    dither.uniforms.uPixel.value = 2 * renderer.getPixelRatio(); // celda de 2 px CSS
    despertar();
  }
  const ro = new ResizeObserver(redimensionar);
  ro.observe(raiz);

  // ---- un único bucle requestAnimationFrame
  let raf = 0, enPantalla = true;
  function frame(t) {
    raf = 0;
    // giro
    let k = 0;
    if (st.anim) {
      const p = clamp((t - st.anim.t0) / DURACION);
      st.pos = st.anim.desde + (st.anim.hasta - st.anim.desde) * st.anim.ease(p);
      k = p < 0.45 ? easeOut(p / 0.45) : 1 - easeInOut((p - 0.45) / 0.55); // respiración: pico al 45 %
      if (p >= 1) { st.pos = st.anim.hasta; st.anim = null; k = 0; }
    }
    pivot.rotation.y = -st.pos * PASO;
    // respiración: la cámara retrocede en Z y el fov pasa de 45 a 48 y vuelve
    camera.position.z = EJE + 0.55 * k;
    camera.fov = L.fov + 3 * k;
    camera.updateProjectionMatrix();
    // mouse-look ±2° con lerp 0.08
    const lk = st.look;
    lk.x += (lk.tx - lk.x) * 0.08; lk.y += (lk.ty - lk.y) * 0.08;
    camera.rotation.set(-lk.y * LOOK, -lk.x * LOOK, 0);
    consolaVista.style.transform = `translate3d(${(-lk.x * 6).toFixed(2)}px,${(-lk.y * 3).toFixed(2)}px,0)`;

    const seg = t / 1000;
    dither.uniforms.uTime.value = seg;
    huecos.forEach((h) => { h.matE.uniforms.uTime.value = seg; });

    scene.updateMatrixWorld();
    colocarRotulos();
    composer.render();
    if (enPantalla && !document.hidden) raf = requestAnimationFrame(frame);
  }
  function despertar() { if (!raf && enPantalla && !document.hidden) raf = requestAnimationFrame(frame); }

  // ---- DOM sobre cada hueco: proyección de sus bordes; opacidad según el ángulo a la cámara
  function proyectar(h, p) {
    v3.copy(p); h.grupo.localToWorld(v3); v3.project(camera);
    return { x: ((v3.x + 1) / 2) * st.ancho, y: ((1 - v3.y) / 2) * st.alto, z: v3.z };
  }
  function colocarRotulos() {
    huecos.forEach((h, i) => {
      if (i >= M) return;
      const d = i - st.pos;
      const r = rotulos[i];
      // la opacidad baja con el ángulo: el texto acompaña a su ventana hasta el lateral
      const ad = Math.abs(d), op = ad <= 0.12 ? 1 : 1 - Math.pow(Math.min(1, (ad - 0.12) / 0.88), 1.4);
      if (ad > 1.6) { r.style.visibility = "hidden"; st.proyecciones[i] = null; return; }
      const iz = proyectar(h, h.ref3.izq), de = proyectar(h, h.ref3.der), ar = proyectar(h, h.ref3.arr), ab = proyectar(h, h.ref3.aba);
      st.proyecciones[i] = { izq: iz.x, der: de.x };
      if (op <= 0 || iz.z > 1 || de.z > 1) { r.style.visibility = "hidden"; return; }
      r.style.visibility = "visible";
      r.style.width = `${Math.max(1, de.x - iz.x).toFixed(1)}px`;
      r.style.height = `${Math.max(1, ab.y - ar.y).toFixed(1)}px`;
      r.style.transform = `translate3d(${iz.x.toFixed(1)}px,${ar.y.toFixed(1)}px,0)`;
      r.style.opacity = op.toFixed(3);
      r.style.pointerEvents = op > 0.9 ? "" : "none";
    });
  }

  // ---- pausa: fuera de pantalla o pestaña oculta
  const io = new IntersectionObserver(([e]) => {
    enPantalla = e.isIntersecting;
    document.documentElement.classList.toggle("in-cab3", e.intersectionRatio > 0.5);
    despertar();
  }, { threshold: [0, 0.5, 1] });
  io.observe(raiz);
  const alVisibilidad = () => despertar();

  raiz.addEventListener("wheel", alRueda, { passive: false });
  addEventListener("scroll", alScroll, { passive: true });
  raiz.addEventListener("pointerdown", alBajar);
  addEventListener("pointermove", alMover);
  addEventListener("pointerup", alSoltar);
  addEventListener("pointercancel", alSoltar);
  addEventListener("keydown", alTeclado);
  document.addEventListener("visibilitychange", alVisibilidad);
  flechas.forEach((b) => b.addEventListener("click", alFlecha));

  redimensionar();
  fijarActivo(0);
  raiz.classList.add("is-ready");

  return () => {
    cancelAnimationFrame(raf);
    ro.disconnect(); io.disconnect();
    document.documentElement.classList.remove("in-cab3");
    raiz.removeEventListener("wheel", alRueda);
    removeEventListener("scroll", alScroll);
    raiz.removeEventListener("pointerdown", alBajar);
    removeEventListener("pointermove", alMover);
    removeEventListener("pointerup", alSoltar);
    removeEventListener("pointercancel", alSoltar);
    removeEventListener("keydown", alTeclado);
    document.removeEventListener("visibilitychange", alVisibilidad);
    flechas.forEach((b) => b.removeEventListener("click", alFlecha));
    volver.removeEventListener("click", cerrarDetalle);
    rotulos.forEach((r) => r.remove());
    desechables.forEach((o) => o.dispose?.());
    fotos.forEach((f) => f.tex.dispose());
    rt.dispose(); composer.dispose?.();
    renderer.dispose(); renderer.domElement.remove();
    raiz.classList.remove("cab3--gl", "is-ready", "is-detalle");
  };
}

// ---------------------------------------------------------------- fallback CSS
function iniciarFallback(raiz, mundos) {
  raiz.classList.add("cab3--css");
  window.__CAB3_MUNDOS = mundos;
  import(/* @vite-ignore */ `/proto/cabina/main.js?v=${Date.now()}`).catch((e) => console.error("[cabina]", e));
  return () => { window.__cab3Cleanup?.(); raiz.classList.remove("cab3--css"); };
}

// ---------------------------------------------------------------- componente
export function Cabina3D({ mundos = [] }) {
  const raiz = useRef(null);
  useEffect(() => {
    const el = raiz.current;
    if (!el || !mundos.length) return undefined;
    const reducido = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reducido || !hayWebGL()) return iniciarFallback(el, mundos);
    el.classList.add("cab3--gl");
    try {
      return iniciarEscena(el, mundos);
    } catch (e) {
      console.warn("[cabina] WebGL falló, uso la versión CSS:", e);
      el.classList.remove("cab3--gl");
      el.querySelectorAll("[data-gl] canvas, [data-rotulos] > *").forEach((n) => n.remove());
      return iniciarFallback(el, mundos);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section ref={raiz} className="cab3" id="mundos" data-cab3="" data-glide="" aria-roledescription="carousel" aria-label="Lo que hace Demeter" tabIndex={0}>
      <h2 className="sr-only">Lo que hace Demeter</h2>
      <p className="sr-only" aria-live="polite" data-anuncio=""></p>
      <div className="cab3__escena" data-escena="">
        <div className="cab3__pared" aria-hidden="true"></div>
        <div className="cab3__gl" data-gl=""></div>
        <div className="cab3__rotulos" data-rotulos=""></div>
        <div className="cab3__vista" data-vista="">
          <div className="cab3__escenario" data-escenario=""><div className="cab3__cilindro" data-cilindro=""></div></div>
        </div>
        <div className="cab3__console" data-consola="">
          <div className="cab3__consola-vista" data-consola-vista="">
            <div className="hud hud--l" aria-hidden="true">
              <svg viewBox="0 0 400 200" preserveAspectRatio="none"><path className="hud__curva" d="M-10 150 C90 150 120 60 230 70 S350 120 420 40" /><path className="hud__curva hud__curva--2" d="M-10 190 C120 180 160 130 260 150 S380 170 420 120" /><circle className="hud__punto" cx="230" cy="70" r="5" /></svg>
            </div>
            <div className="hud hud--c">
              <p className="hud__hint">Desliza para explorar</p>
              <div className="hud__nav">
                <button type="button" className="hud__flecha" data-paso="-1" aria-label="Mundo anterior"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3 5 8l5 5" /></svg></button>
                <span className="hud__dots" data-puntos=""></span>
                <button type="button" className="hud__flecha" data-paso="1" aria-label="Mundo siguiente"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="m6 3 5 5-5 5" /></svg></button>
              </div>
              <p className="hud__read mono" data-lectura=""></p>
            </div>
            <div className="hud hud--r" aria-hidden="true">
              <svg viewBox="0 0 400 200" preserveAspectRatio="none"><circle className="hud__radar" cx="250" cy="210" r="150" /><circle className="hud__radar" cx="250" cy="210" r="95" /><circle className="hud__radar" cx="250" cy="210" r="40" /><circle className="hud__punto hud__punto--2" cx="300" cy="120" r="5" /></svg>
            </div>
          </div>
        </div>
      </div>
      <div className="cab3__detail" data-detalle="" role="dialog" aria-modal="true" aria-label="Detalle del proyecto">
        <article className="cab3__card" data-tarjeta="">
          <img data-d-img="" src={mundos[0]?.img} alt="" draggable="false" />
          <div className="cab3__card-body">
            <h3 data-d-pregunta=""></h3>
            <p data-d-texto=""></p>
            <a className="cab3__ver" data-d-ver="" href="/dashboard">Ver proyecto</a>
          </div>
        </article>
        <button type="button" className="cab3__volver" data-d-volver="">Explorar otros proyectos</button>
      </div>
    </section>
  );
}
