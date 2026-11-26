// Demeter · cuándo se quita (y se vuelve a poner) la pantalla de carga del aguacate.
//
// La pantalla en sí es CSS (carga.css, pseudo-elementos de <html>) y se ve desde el primer pintado.
// Aquí solo se decide cuándo poner `dm-listo` en <html>:
//  · Al abrir la web: cuando React ha pintado la página (.dm-shell), los scripts del prototipo han
//    terminado (prototipo.py marca <html data-dm-scripts> mientras cargan), las fuentes están y el
//    documento ha cargado. Como mínimo se ve MINIMO ms (que dé una vuelta y no sea un destello).
//  · Al navegar dentro de la app: la pantalla solo aparece si la página nueva tarda más de
//    RETRASO_NAV ms; si llega antes, no se ve nada.
// Por seguridad, nunca se queda más de MAXIMO ms.
(() => {
  if (window.__dmCarga) return;
  window.__dmCarga = true;

  const MINIMO = 700, RETRASO_NAV = 180, MAXIMO = 8000, ESTABLE = 2;
  const raiz = document.documentElement;
  let visibleDesde = performance.now(), desde = performance.now(), shellAnterior = null;
  let sondeo = 0, retraso = 0, tope = 0, estable = 0, navegando = false;

  const lista = () => {
    if (raiz.hasAttribute("data-dm-scripts") || document.readyState !== "complete") return false;
    if (document.fonts && document.fonts.status !== "loaded") return false;
    const shell = document.querySelector(".dm-shell"), pasado = performance.now() - desde;
    // Al abrir la web hace falta la página pintada (sin ella solo hay fondo en blanco). Al navegar,
    // la página nueva es otro .dm-shell; si React reutiliza el mismo nodo, o la página no usa
    // layout(), se da por buena al cabo de un rato.
    if (!shell) return navegando && pasado > 2500;
    return shell !== shellAnterior || pasado > 1200;
  };
  const visible = () => !raiz.classList.contains("dm-listo");

  function ocultar() {
    clearInterval(sondeo); clearTimeout(retraso); clearTimeout(tope);
    sondeo = 0;
    if (!visible()) return;
    const espera = Math.max(0, MINIMO - (performance.now() - visibleDesde));
    setTimeout(() => raiz.classList.add("dm-listo"), espera);
  }
  function mostrar() {
    if (visible()) return;
    visibleDesde = performance.now();
    raiz.classList.remove("dm-listo");
  }
  function vigilar() {
    clearInterval(sondeo);
    desde = performance.now();
    estable = 0;
    // varias comprobaciones seguidas: entre que aparece la página y empiezan sus scripts hay un hueco
    sondeo = setInterval(() => { estable = lista() ? estable + 1 : 0; if (estable >= ESTABLE) ocultar(); }, 90);
    clearTimeout(tope);
    tope = setTimeout(ocultar, MAXIMO);
  }

  // ---- al abrir la web
  vigilar();

  // ---- al navegar (react-router usa history.pushState; atrás/adelante, popstate)
  let ruta = location.pathname;
  function alNavegar() {
    if (location.pathname === ruta) return;
    ruta = location.pathname;
    navegando = true;
    shellAnterior = document.querySelector(".dm-shell"); // la página vieja: hay que esperar a otra
    clearTimeout(retraso);
    retraso = setTimeout(mostrar, RETRASO_NAV);
    vigilar();
  }
  const pushState = history.pushState;
  history.pushState = function (...args) { const r = pushState.apply(this, args); alNavegar(); return r; };
  addEventListener("popstate", alNavegar);
})();
