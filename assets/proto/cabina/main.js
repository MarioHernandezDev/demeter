// Fallback CSS de la sección «mundos» (sin WebGL o con «reducir movimiento»). La versión normal es la
// escena three.js de demeter/components/cabina3d.jsx, que carga este archivo solo cuando hace falta.
// GSAP (Observer + CustomEase) viene de cdnjs con versión fija. Los datos, de mundos.json.
import { crearVentana } from './world.js';
import { crearCarrusel } from './carousel.js';
import { crearCabina } from './cabin.js';
import { crearDetalle } from './detail.js';

const GSAP = 'https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/';
const cargar = (src) => new Promise((ok, ko) => {
  const s = document.createElement('script');
  s.src = src; s.onload = ok; s.onerror = () => ko(new Error(`No se pudo cargar ${src}`));
  document.head.appendChild(s);
});

async function iniciar() {
  window.__cab3Cleanup?.();
  const turno = (window.__cab3Turno = Symbol('cab3')); // si la portada se monta dos veces, solo gana la última
  const raiz = document.querySelector('[data-cab3]');
  if (!raiz) return;

  if (!window.gsap) await cargar(`${GSAP}gsap.min.js`);
  if (!window.Observer) await cargar(`${GSAP}Observer.min.js`);
  if (!window.CustomEase) await cargar(`${GSAP}CustomEase.min.js`);
  const { gsap, Observer, CustomEase } = window;
  gsap.registerPlugin(Observer, CustomEase);
  CustomEase.create('cabina', 'M0,0 C0.16,1 0.3,1 1,1'); // de salida: arranca ya y frena
  if (!raiz.isConnected || window.__cab3Turno !== turno) return; // la página cambió mientras cargaba GSAP

  const MUNDOS = window.__CAB3_MUNDOS || (await (await fetch('/proto/cabina/mundos.json')).json());
  if (!raiz.isConnected || window.__cab3Turno !== turno) return;

  const reducido = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const $ = (s) => raiz.querySelector(s);
  const escena = $('[data-escena]'), cilindro = $('[data-cilindro]'), escenario = $('[data-escenario]');
  const consola = $('[data-consola]'), puntosEl = $('[data-puntos]'), lectura = $('[data-lectura]');
  const anuncio = $('[data-anuncio]');

  // ---- ventanas
  cilindro.replaceChildren();
  const ventanas = MUNDOS.map((m, i) => crearVentana(m, i, MUNDOS.length));

  // ---- paginación: botones reales (el activo en blanco, el resto al 40 %)
  puntosEl.replaceChildren(...MUNDOS.map((m, i) => {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'hud__dot'; b.setAttribute('aria-label', `Ir a ${m.titulo}`);
    b.addEventListener('click', () => carrusel.irAIndice(i));
    return b;
  }));
  const puntos = [...puntosEl.children];

  // ---- detalle («Explorar»)
  const detalle = crearDetalle({ gsap, raiz, escena, consola, detalle: $('[data-detalle]'), reducido });

  const alCambiar = (i) => {
    const m = MUNDOS[i];
    puntos.forEach((p, k) => { p.classList.toggle('is-on', k === i); p.setAttribute('aria-current', k === i ? 'true' : 'false'); });
    gsap.fromTo(lectura, { autoAlpha: 0, y: 6 }, { autoAlpha: 1, y: 0, duration: reducido ? 0.3 : 0.6, delay: reducido ? 0 : 0.3, ease: 'power3.out' });
    lectura.textContent = m.lectura;
    anuncio.textContent = `${m.titulo}. ${m.sub}`;
  };

  const carrusel = crearCarrusel({
    gsap, Observer, raiz, escenario, cilindro, ventanas, reducido, alCambiar,
    hayDetalle: () => detalle.abierto,
  });
  ventanas.forEach((v, i) => v.cta.addEventListener('click', () => detalle.abrir(MUNDOS[i])));
  raiz.querySelectorAll('[data-paso]').forEach((b) => b.addEventListener('click', () => carrusel.paso(Number(b.dataset.paso))));

  // Sin tope no hay «final» al que llegar con la rueda: ↓ / Re Pág bajan por la portada y ↑ / Av Pág suben.
  const alTecla = (e) => {
    if (detalle.abierto || e.altKey || e.ctrlKey || e.metaKey) return;
    const r = raiz.getBoundingClientRect();
    if (Math.abs(r.top) > innerHeight * 0.12) return;
    if (['ArrowDown', 'PageDown'].includes(e.key)) { e.preventDefault(); document.getElementById('gemelo')?.scrollIntoView({ behavior: reducido ? 'auto' : 'smooth' }); }
    if (['ArrowUp', 'PageUp'].includes(e.key)) { e.preventDefault(); scrollTo({ top: raiz.offsetTop - innerHeight, behavior: reducido ? 'auto' : 'smooth' }); }
  };
  addEventListener('keydown', alTecla);

  const cabina = crearCabina({ raiz, vista: $('[data-vista]'), consolaVista: $('[data-consola-vista]'), reducido, respiracion: () => carrusel.resp });

  const vigia = new IntersectionObserver(([e]) => document.documentElement.classList.toggle('in-cab3', e.intersectionRatio > 0.5), { threshold: [0, 0.5, 1] });
  vigia.observe(raiz);

  window.__cab3Cleanup = () => {
    vigia.disconnect(); document.documentElement.classList.remove('in-cab3');
    carrusel.destruir(); cabina.destruir(); detalle.destruir();
    removeEventListener('keydown', alTecla);
  };
  raiz.classList.add('is-ready');
}

iniciar().catch((e) => console.error('[cabina]', e));
