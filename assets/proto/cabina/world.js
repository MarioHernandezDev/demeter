// World (versión CSS, fallback sin WebGL o con «reducir movimiento»): una ventana con su mundo en capas.
// Capas de dentro afuera (la velocidad es cuánto se desplazan al girar la cabina):
//   foto del mundo .15 · montaña lejana .30 · montaña cercana .50 · estrellas y polvo .60
// Al girar, cada capa se mueve en sentido contrario a la ventana, así parece un mundo real tras el cristal.
const SVG = 'http://www.w3.org/2000/svg';

const el = (tag, cls, attrs = {}, ns) => {
  const n = ns ? document.createElementNS(SVG, tag) : document.createElement(tag);
  if (cls) n.setAttribute('class', cls);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
};

// Aleatorio determinista (mismas estrellas en cada carga).
const rng = (seed) => () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;

function silueta(clase, vel, d, color, alpha, alto) {
  const capa = el('div', `lyr lyr--${clase}`);
  const svg = el('svg', null, { viewBox: '0 0 1600 600', preserveAspectRatio: 'none', 'aria-hidden': 'true' }, true);
  svg.style.height = alto;
  svg.appendChild(el('path', null, { d, fill: color, 'fill-opacity': alpha }, true));
  capa.appendChild(svg);
  return { nodo: capa, vel };
}

function particulas(m, indice) {
  const capa = el('div', 'lyr lyr--fx');
  const svg = el('svg', null, { viewBox: '0 0 1600 1000', preserveAspectRatio: 'xMidYMid slice', 'aria-hidden': 'true' }, true);
  const azar = rng(97 + indice * 31);
  for (let i = 0; i < 26; i++) {
    const c = el('circle', 'star', { cx: (azar() * 1600).toFixed(0), cy: (azar() * 640).toFixed(0), r: (1 + azar() * 2.4).toFixed(1), fill: m.colores.particula }, true);
    c.style.animationDelay = `${(azar() * 4).toFixed(2)}s`;
    c.style.animationDuration = `${(3 + azar() * 4).toFixed(2)}s`;
    svg.appendChild(c);
  }
  if (m.constelacion) {
    const pts = m.constelacion.map(([x, y]) => [x * 16, y * 10]);
    svg.appendChild(el('polyline', 'const', { points: pts.map((p) => p.join(',')).join(' '), fill: 'none', stroke: m.colores.particula }, true));
    pts.forEach(([x, y]) => svg.appendChild(el('circle', 'const-dot', { cx: x, cy: y, r: 5, fill: m.colores.particula }, true)));
  }
  capa.appendChild(svg);
  return { nodo: capa, vel: 0.6 };
}

/** Crea la ventana del mundo `m`. Devuelve su nodo, sus capas y sus textos. */
export function crearVentana(m, indice, total) {
  const win = el('section', 'win', { 'aria-roledescription': 'slide', 'aria-label': `${indice + 1} de ${total}: ${m.titulo}` });
  const marco = el('div', 'win__frame');
  const cristal = el('div', 'win__glass');

  const foto = el('div', 'lyr lyr--photo');
  const img = el('img', null, { src: m.img, alt: m.alt, draggable: 'false', decoding: 'async' });
  foto.classList.add('lyr--ancha');
  foto.appendChild(img);

  const capas = [
    { nodo: foto, vel: 0.15 },
    silueta('far', 0.3, 'M0 600V430L160 360L320 410L520 290L720 400L900 330L1100 410L1300 340L1480 400L1600 370V600Z', m.colores.lejos, 0.4, '46%'),
    silueta('near', 0.5, 'M0 600V500C200 440 300 520 520 478S900 420 1100 488S1450 455 1600 500V600Z', m.colores.cerca, 0.72, '30%'),
    particulas(m, indice),
  ];
  capas.forEach((c) => cristal.appendChild(c.nodo));
  cristal.appendChild(el('div', 'win__shade'));

  const texto = el('div', 'win__text');
  const titulo = el('h3', 'win__title');
  titulo.textContent = m.titulo;
  const sub = el('p', 'win__sub');
  sub.textContent = m.sub;
  texto.append(titulo, sub);

  const cta = el('button', 'win__cta', { type: 'button' });
  cta.textContent = 'Explorar';
  cristal.append(texto, cta);

  marco.append(cristal, el('span', 'win__bevel', { 'aria-hidden': 'true' }));
  win.appendChild(marco);
  if (m.velo) { win.classList.add('win--velo'); win.style.setProperty('--velo', String(m.velo)); }
  return { nodo: win, capas, titulo, sub, cta };
}

/** Desplaza las capas según la distancia `d` (en ventanas) al centro; `ancho` es el ancho de la ventana. */
export function paralaje(v, d, ancho) {
  for (const c of v.capas) {
    c.nodo.style.transform = `translate3d(${(-d * c.vel * ancho).toFixed(1)}px,0,0)`;
  }
}
