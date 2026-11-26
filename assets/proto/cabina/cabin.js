// Cabin: la escena. Un ÚNICO bucle requestAnimationFrame para todo:
//   · mouse-look con inercia (lerp 0.08): rotateY ±2°, rotateX ±1.5° y un pequeño desplazamiento
//   · «respiración» de cámara durante el giro del cilindro (scale 1 → 0.94 → 1)
//   · cualquier otra cosa que se suscriba con `suscribir(fn)` (grano, shaders de las fotos…)
// Se pausa si la sección no está en pantalla o si la pestaña está oculta.

export function crearCabina({ raiz, vista, consolaVista, reducido, respiracion }) {
  const fino = matchMedia('(pointer: fine)').matches && innerWidth > 760;
  const obj = { x: 0, y: 0 }, act = { x: 0, y: 0 };
  const suscritos = new Set();
  let raf = 0, activa = true, enPantalla = true;

  const alMover = (e) => {
    const r = raiz.getBoundingClientRect();
    obj.x = ((e.clientX - r.left) / r.width) * 2 - 1;
    obj.y = ((e.clientY - r.top) / r.height) * 2 - 1;
  };
  const alSalir = () => { obj.x = 0; obj.y = 0; };

  const bucle = (t) => {
    act.x += (obj.x - act.x) * 0.08;
    act.y += (obj.y - act.y) * 0.08;
    const k = respiracion ? respiracion() : 0;
    vista.style.transform = `translate3d(${(-act.x * 14).toFixed(2)}px,${(-act.y * 8).toFixed(2)}px,0) scale(${(1 - 0.06 * k).toFixed(4)}) rotateY(${(act.x * 2).toFixed(3)}deg) rotateX(${(-act.y * 1.5).toFixed(3)}deg)`;
    consolaVista.style.transform = `translate3d(${(-act.x * 6).toFixed(2)}px,${(-act.y * 3).toFixed(2)}px,0)`;
    suscritos.forEach((fn) => fn(t));
    raf = requestAnimationFrame(bucle);
  };
  const parar = () => { cancelAnimationFrame(raf); raf = 0; };
  const arrancar = () => { if (!raf && activa && enPantalla && !reducido) raf = requestAnimationFrame(bucle); };
  const actualizar = () => { activa = !document.hidden; (activa && enPantalla) ? arrancar() : parar(); };

  document.addEventListener('visibilitychange', actualizar);
  const io = new IntersectionObserver(([e]) => { enPantalla = e.isIntersecting; actualizar(); }, { threshold: 0.05 });
  io.observe(raiz);

  if (fino && !reducido) {
    raiz.addEventListener('pointermove', alMover);
    raiz.addEventListener('pointerleave', alSalir);
  }
  arrancar();

  return {
    suscribir(fn) { suscritos.add(fn); return () => suscritos.delete(fn); },
    get enPantalla() { return enPantalla && activa; },
    destruir() {
      parar();
      io.disconnect();
      suscritos.clear();
      document.removeEventListener('visibilitychange', actualizar);
      raiz.removeEventListener('pointermove', alMover);
      raiz.removeEventListener('pointerleave', alSalir);
    },
  };
}
