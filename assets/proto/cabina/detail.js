// ProjectDetail: lo que pasa al pulsar «Explorar».
//  1) la cámara «sale» de la cabina (escena arriba y un poco más grande, la consola baja)
//  2) fundido a un degradado con desenfoque
//  3) aparece la tarjeta: imagen, pregunta, texto y botón, uno tras otro
//  4) «Explorar otros proyectos» (o Esc) deshace la secuencia al revés.
export function crearDetalle({ gsap, raiz, escena, consola, detalle, reducido }) {
  const fondo = detalle;
  const tarjeta = detalle.querySelector('[data-tarjeta]');
  const imagen = detalle.querySelector('[data-d-img]');
  const pregunta = detalle.querySelector('[data-d-pregunta]');
  const texto = detalle.querySelector('[data-d-texto]');
  const ver = detalle.querySelector('[data-d-ver]');
  const volver = detalle.querySelector('[data-d-volver]');
  let abierto = false, ultimoFoco = null;

  gsap.set(fondo, { autoAlpha: 0 });

  const d = reducido ? 0.3 : 1;
  const tl = gsap.timeline({ paused: true, defaults: { ease: 'power3.out' } })
    .to(escena, { yPercent: -15, scale: 1.08, duration: 0.6 * d, ease: 'power2.inOut' }, 0)
    .to(consola, { yPercent: 130, autoAlpha: 0, duration: 0.5 * d }, 0)
    .to(escena, { autoAlpha: 0, duration: 0.4 * d }, 0.35 * d)
    .to(fondo, { autoAlpha: 1, duration: 0.5 * d }, 0.3 * d)
    .fromTo(imagen, { y: 16, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: 0.55 * d }, 0.75 * d)
    .fromTo([pregunta, texto, ver], { y: 16, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: 0.5 * d, stagger: 0.12 * d }, 0.95 * d)
    .fromTo(volver, { y: 12, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: 0.45 * d }, 1.35 * d);

  function abrir(m) {
    if (abierto) return;
    abierto = true;
    ultimoFoco = document.activeElement;
    imagen.src = m.img;
    imagen.alt = m.alt;
    pregunta.textContent = m.pregunta;
    texto.textContent = m.texto;
    ver.textContent = 'Ver proyecto';
    ver.href = m.href;
    escena.setAttribute('inert', '');
    tl.timeScale(1).play();
    tl.eventCallback('onComplete', () => ver.focus({ preventScroll: true }));
  }

  function cerrar() {
    if (!abierto) return;
    abierto = false;
    tl.eventCallback('onComplete', null);
    tl.timeScale(1.15).reverse();
    tl.eventCallback('onReverseComplete', () => {
      escena.removeAttribute('inert');
      gsap.set(escena, { clearProps: 'transform' });
      ultimoFoco?.focus?.({ preventScroll: true });
    });
  }

  volver.addEventListener('click', cerrar);
  const alTecla = (e) => { if (abierto && e.key === 'Escape') cerrar(); };
  addEventListener('keydown', alTecla);

  return {
    abrir, cerrar,
    get abierto() { return abierto; },
    destruir() { tl.kill(); removeEventListener('keydown', alTecla); volver.removeEventListener('click', cerrar); },
  };
}
