// WindowCarousel: las ventanas sobre una pared curva (cilindro) y todo lo que las mueve.
//
// Geometría: la cámara está en el centro del cilindro (perspective = R). Cada ventana va en
//   translateZ(R - atrás) rotateY(a) translateZ(-R)      con a = -d · ANG
// donde `d` es su distancia al centro en ventanas. Girar la cabina es cambiar `estado.pos`: la que entra llega por la
// derecha girando de -ANG a 0; la que sale se va por la izquierda de 0 a +ANG y se aleja en Z.
// El parallax de las capas se calcula en `pintar()` a partir de ese mismo ángulo, en cada frame.
//
// Sin bucle: los mundos van del primero al último. La rueda avanza de uno en uno y, en el primero
// (hacia arriba) y el último (hacia abajo), deja que la página siga; flechas, puntos y arrastre se
// paran en los extremos (el arrastre con rebote elástico).
import { paralaje } from './world.js';

const UMBRAL_RUEDA = 55; // delta acumulado para avanzar una ventana
const RESISTENCIA = 0.35; // el cilindro sigue al dedo con esta resistencia
const DURACION = 1.3; // s
const COOLDOWN_RUEDA = 400; // ms sin capturar la rueda tras soltarla en un extremo
const mod = (n, m) => ((n % m) + m) % m;
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));

export function crearCarrusel({ gsap, Observer, raiz, escenario, cilindro, ventanas, reducido, alCambiar, hayDetalle }) {
  const N = ventanas.length;
  const estado = { pos: 0, resp: 0 }; // resp: respiración de cámara, 0 → 1 → 0 durante el giro
  let R = 1600, ANG = 28, ancho = 800;
  let destino = 0, anim = null, resp = null, bloqueado = false, activo = 0;
  let arrastrando = false, arrastreHecho = false, base = 0;

  ventanas.forEach((v) => cilindro.appendChild(v.nodo));

  // ---- geometría: depende del tamaño de la ventana del navegador
  function medir() {
    const vw = innerWidth, movil = vw <= 760;
    ancho = ventanas[0].nodo.offsetWidth || vw * 0.55;
    ANG = movil ? 34 : 28;
    const visible = movil ? 0.05 : 0.2; // fracción de la vecina que asoma por el borde
    const wVecina = ancho * 0.9;
    const centro = vw / 2 - visible * wVecina + wVecina / 2;
    R = centro / Math.tan((ANG * Math.PI) / 180);
    escenario.style.perspective = `${R.toFixed(0)}px`;
    pintar();
  }

  function pintar() {
    // Empuje de cámara: todo el cilindro retrocede un poco en Z durante el giro.
    cilindro.style.transform = `translateZ(${(-estado.resp * R * 0.1).toFixed(1)}px)`;
    ventanas.forEach((v, i) => {
      const d = i - estado.pos;
      const ad = Math.abs(d);
      const op = ad <= 1.15 ? 1 : clamp(1 - (ad - 1.15) / 0.45);
      const s = 1 - 0.06 * Math.min(ad, 1.5);
      const atras = Math.min(ad, 1.5) * R * 0.1; // las que se alejan del centro también se alejan en Z
      const n = v.nodo;
      n.style.transform = `translateZ(${(R - atras).toFixed(1)}px) rotateY(${(-d * ANG).toFixed(3)}deg) translateZ(${(-R).toFixed(1)}px) scale(${s.toFixed(4)})`;
      n.style.opacity = op.toFixed(3);
      n.style.visibility = op <= 0 ? 'hidden' : 'visible';
      n.style.zIndex = String(Math.round(100 - ad * 10));
      v.visible = op > 0;
      if (v.visible) paralaje(v, d, ancho);
    });
  }

  // ---- ventana activa: textos, foco y paginación
  function fijarActivo(i) {
    if (i === activo && ventanas[i].nodo.classList.contains('is-active')) return;
    activo = i;
    ventanas.forEach((v, k) => {
      const on = k === i;
      v.nodo.classList.toggle('is-active', on);
      v.cta.tabIndex = on ? 0 : -1;
      v.nodo.setAttribute('aria-hidden', on ? 'false' : 'true');
      const piezas = [v.titulo, v.sub, v.cta];
      gsap.killTweensOf(piezas);
      if (on) {
        gsap.fromTo(piezas, { y: reducido ? 0 : 20, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: reducido ? 0.3 : 0.7, delay: reducido ? 0 : 0.35, stagger: 0.06, ease: 'power3.out' });
      } else {
        gsap.to(piezas, { autoAlpha: 0, duration: 0.25, ease: 'power1.out' });
      }
    });
    raiz.querySelectorAll('[data-paso]').forEach((b) => { const d = Number(b.dataset.paso); b.disabled = (d < 0 && i === 0) || (d > 0 && i === N - 1); });
    alCambiar?.(i);
  }

  // ---- navegación
  function irA(abs) {
    if (hayDetalle?.()) return;
    abs = Math.min(N - 1, Math.max(0, abs));
    destino = abs;
    fijarActivo(abs);
    anim?.kill();
    resp?.kill();
    bloqueado = true;
    if (reducido) {
      gsap.fromTo(cilindro, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.3 });
      estado.pos = abs; estado.resp = 0; pintar(); bloqueado = false;
      return;
    }
    anim = gsap.to(estado, {
      pos: abs, duration: DURACION, ease: 'cabina', onUpdate: pintar,
      onComplete: () => { bloqueado = false; },
    });
    // «Respiración»: la cámara se echa atrás y vuelve, con el pico al 45 % del giro.
    resp = gsap.timeline({ onUpdate: pintar })
      .to(estado, { resp: 1, duration: DURACION * 0.45, ease: 'power2.out' })
      .to(estado, { resp: 0, duration: DURACION * 0.55, ease: 'power2.inOut' });
  }
  const paso = (delta) => { if (!bloqueado || arrastrando) irA(Math.round(arrastrando ? base : destino) + delta); };
  const irAIndice = (i) => { if (i !== activo) irA(i); };

  // ---- rueda / trackpad: acumulador con umbral y bloqueo mientras dura la transición
  let acc = 0, ultimoEvento = 0, ultimoAbs = 0, libreHasta = 0, idRueda = 0, sueltaHasta = 0;
  const enVista = () => { const r = raiz.getBoundingClientRect(); return Math.abs(r.top) < innerHeight * 0.12 && r.bottom > innerHeight * 0.88; };
  const alRueda = (e) => {
    const ahora = performance.now();
    if (!enVista() || hayDetalle?.() || ahora < sueltaHasta) return;
    const delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
    const abs = Math.abs(delta);
    const enExtremo = (delta > 0 && activo >= N - 1) || (delta < 0 && activo <= 0);
    // En el primer o último mundo el scroll sigue por la página, salvo si acaba de llegar (inercia del gesto).
    if (!enExtremo || bloqueado || ahora < libreHasta) e.preventDefault();
    // La inercia del trackpad sigue enviando eventos con delta cada vez menor: no cuentan como gesto nuevo.
    const nuevo = ahora - ultimoEvento > 140 || abs > ultimoAbs * 1.15;
    ultimoEvento = ahora; ultimoAbs = abs;
    if (bloqueado || ahora < libreHasta) return;
    if (ahora - idRueda > 180) acc = 0;
    if (acc === 0 && !nuevo) { if (enExtremo) e.preventDefault(); return; }
    if (enExtremo) { acc = 0; sueltaHasta = ahora + COOLDOWN_RUEDA; return; } // gesto nuevo hacia fuera: la página baja o sube
    idRueda = ahora;
    acc += delta;
    if (Math.abs(acc) >= UMBRAL_RUEDA) {
      const d = Math.sign(acc); acc = 0;
      libreHasta = ahora + DURACION * 1000 + 120;
      paso(d);
    }
  };
  raiz.addEventListener('wheel', alRueda, { passive: false });

  // ---- arrastre con ratón o dedo (GSAP Observer): el cilindro sigue al puntero en tiempo real
  const observer = Observer.create({
    target: raiz, type: 'touch,pointer', dragMinimum: 6, lockAxis: true, allowClicks: true, tolerance: 6,
    ignore: '.win__cta, .cab3__console a, .cab3__console button, .cab3__detail',
    onDragStart: () => {
      if (hayDetalle?.()) return;
      arrastrando = true; arrastreHecho = true; anim?.kill(); resp?.kill(); bloqueado = false;
      estado.resp = 0; base = estado.pos;
    },
    onDrag: (s) => {
      if (!arrastrando) return;
      const dx = s.x - s.startX;
      // Sigue al puntero (con resistencia) y puede quedarse a medio camino mientras arrastras.
      const libre = base - (dx * RESISTENCIA) / (ancho * 0.3);
      estado.pos = libre < 0 ? libre / 3 : libre > N - 1 ? N - 1 + (libre - (N - 1)) / 3 : libre; // rubber band
      pintar();
    },
    onDragEnd: (s) => {
      if (!arrastrando) return;
      arrastrando = false;
      const dx = s.x - s.startX, v = s.velocityX;
      const origen = Math.round(base);
      if (Math.abs(dx) > 70 || Math.abs(v) > 600) irA(origen + (dx < 0 || v < -600 ? 1 : -1));
      else irA(origen); // vuelve a la ventana actual con un snap
      setTimeout(() => { arrastreHecho = false; }, 0);
    },
  });

  // ---- clic en una ventana lateral: navega a ella
  const alClic = (e) => {
    if (arrastreHecho) return;
    const w = e.target.closest?.('.win');
    if (!w || e.target.closest('.win__cta')) return;
    const i = ventanas.findIndex((v) => v.nodo === w);
    if (i >= 0 && i !== activo) irAIndice(i);
  };
  cilindro.addEventListener('click', alClic);

  // ---- teclado ← → (con la cabina a la vista)
  const alTeclado = (e) => {
    if (hayDetalle?.() || e.altKey || e.ctrlKey || e.metaKey) return;
    if (!enVista() && !raiz.contains(document.activeElement)) return;
    if (e.key === 'ArrowRight') { e.preventDefault(); paso(1); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); paso(-1); }
  };
  addEventListener('keydown', alTeclado);

  addEventListener('resize', medir);
  medir();
  fijarActivo(0);
  requestAnimationFrame(medir);

  return {
    paso, irAIndice, medir,
    get resp() { return estado.resp; },
    get activo() { return activo; },
    destruir() {
      anim?.kill(); resp?.kill();
      observer.kill();
      raiz.removeEventListener('wheel', alRueda);
      cilindro.removeEventListener('click', alClic);
      removeEventListener('keydown', alTeclado);
      removeEventListener('resize', medir);
    },
  };
}
