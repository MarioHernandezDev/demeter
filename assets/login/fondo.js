// Fondo «Aurora» del login (/login): cortinas de luz en WebGL con la paleta de Demeter
// (olivo -> papel -> terracota) que se levantan cerca del puntero, y la palabra «Demeter»
// gigante ajustada al ancho de la página. Solo decoración (aria-hidden).
// Sin ratón fino o con prefers-reduced-motion se pinta una vez, quieto.
window.__loginFondoOff?.();

const stage = document.querySelector(".pl-login");
const fine = matchMedia("(hover: hover) and (pointer: fine)").matches;
const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;

const VERT = "attribute vec2 p; void main(){ gl_Position = vec4(p, 0., 1.); }";
const HEAD = `precision highp float;
uniform vec2 uRes; uniform float uTime; uniform vec3 uPtr; uniform float uReveal;
const vec3 OLIVE = vec3(.243, .353, .133);
const vec3 TERRA = vec3(.702, .227, .071);
const vec3 PAPER = vec3(.925, .933, .929);
const vec3 INK   = vec3(.055, .078, .067);
float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
vec3 permute(vec3 x){ return mod(((x * 34.) + 1.) * x, 289.); }
float snoise(vec2 v){
  const vec4 C = vec4(.211324865405187, .366025403784439, -.577350269189626, .024390243902439);
  vec2 i = floor(v + dot(v, C.yy)); vec2 x0 = v - i + dot(i, C.xx);
  vec2 i1 = (x0.x > x0.y) ? vec2(1., 0.) : vec2(0., 1.);
  vec4 x12 = x0.xyxy + C.xxzz; x12.xy -= i1; i = mod(i, 289.);
  vec3 p = permute(permute(i.y + vec3(0., i1.y, 1.)) + i.x + vec3(0., i1.x, 1.));
  vec3 m = max(.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy), dot(x12.zw, x12.zw)), 0.); m = m * m; m = m * m;
  vec3 x = 2. * fract(p * C.www) - 1.; vec3 h = abs(x) - .5; vec3 ox = floor(x + .5); vec3 a0 = x - ox;
  m *= 1.79284291400159 - .85373472095314 * (a0 * a0 + h * h);
  vec3 g; g.x = a0.x * x0.x + h.x * x0.y; g.yz = a0.yz * x12.xz + h.yz * x12.yw;
  return 130. * dot(m, g);
}
`;

// Aurora: cortinas de ruido que cuelgan de arriba, olivo -> papel -> terracota; el puntero las levanta.
const AURORA_FN = `
vec3 ramp(float t){
  vec3 pale = mix(OLIVE, PAPER, .55);
  return t < .5 ? mix(OLIVE * 1.25, pale, t * 2.) : mix(pale, TERRA * 1.15, (t - .5) * 2.);
}
vec3 aurora(){
  vec2 uv = gl_FragCoord.xy / uRes;
  float y = 1. - uv.y, t = uTime * .1;
  vec3 col = INK; float lift = uPtr.z * exp(-pow((uv.x - uPtr.x) / .38, 2.));
  for (int i = 0; i < 2; i++) {
    float fi = float(i);
    float h = snoise(vec2(uv.x * (1.5 + fi * .9) + t * (2. + fi), t * (.7 + fi * .3) + fi * 9.)) * .5 + .5;
    float edge = .18 + .5 * h + lift * .22 - fi * .06;
    float a = (1. - smoothstep(edge - .04, edge + .38, y)) * (.3 + .7 * h);
    float glow = exp(-abs(y - edge) * 5.) * .5;
    float cx = clamp(uv.x + .25 * snoise(vec2(uv.x * 1.2 + fi * 4., t)), 0., 1.);
    col += ramp(cx) * (a * .62 + glow * .45) * (1. - fi * .35);
  }
  return col;
}`;
const FIN = `
vec3 finish(vec3 col){
  col *= uReveal;
  return col + (hash(gl_FragCoord.xy + uTime) - .5) / 90.;
}`;
const AURORA = HEAD + AURORA_FN + FIN + `
void main(){ gl_FragColor = vec4(finish(aurora()), 1.); }`;
if (stage) {
  const canvas = stage.querySelector(".pl4__fx");
  const follow = fine && !calm;
  const gl = canvas?.getContext("webgl", { antialias: false, alpha: false, powerPreference: "low-power" });
  let prog = null, raf = 0, last = 0, clock = 0, reveal = 0;
  const ptr = { x: .5, y: .5, tx: .5, ty: .5, reach: 0, treach: 0 };

  if (gl) {
    const mk = (type, src) => { const sh = gl.createShader(type); gl.shaderSource(sh, src); gl.compileShader(sh); return sh; };
    const pr = gl.createProgram();
    gl.attachShader(pr, mk(gl.VERTEX_SHADER, VERT));
    gl.attachShader(pr, mk(gl.FRAGMENT_SHADER, AURORA));
    gl.bindAttribLocation(pr, 0, "p");
    gl.linkProgram(pr);
    if (gl.getProgramParameter(pr, gl.LINK_STATUS)) {
      prog = { pr, u: ["uRes", "uTime", "uPtr", "uReveal"].map((n) => gl.getUniformLocation(pr, n)) };
      // Un triángulo que cubre toda la pantalla.
      gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    } else {
      console.warn(gl.getProgramInfoLog(pr));
    }
  }

  const size = () => {
    if (!prog) return;
    const s = Math.min(devicePixelRatio || 1, 1.5) * .75; // algo por debajo de la pantalla: son degradados suaves
    canvas.width = Math.max(2, Math.round(canvas.clientWidth * s));
    canvas.height = Math.max(2, Math.round(canvas.clientHeight * s));
    gl.viewport(0, 0, canvas.width, canvas.height);
  };
  const draw = () => {
    if (!prog) return;
    gl.useProgram(prog.pr);
    gl.uniform2f(prog.u[0], canvas.width, canvas.height);
    gl.uniform1f(prog.u[1], clock);
    gl.uniform3f(prog.u[2], ptr.x, 1 - ptr.y, ptr.reach);
    gl.uniform1f(prog.u[3], reveal);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  };
  const tick = (now) => {
    raf = 0;
    // Reflex cambia de página sin recargar: si el login ya no está, se para todo.
    if (!stage.isConnected) { window.__loginFondoOff?.(); return; }
    if (document.hidden) return;
    const dt = Math.min(.05, Math.max(.0005, (now - last) / 1000)); last = now;
    clock += dt;
    reveal = Math.min(1, reveal + dt / 1.6);
    const f = 1 - Math.exp(-dt / .45);
    ptr.x += (ptr.tx - ptr.x) * f; ptr.y += (ptr.ty - ptr.y) * f;
    ptr.reach += (ptr.treach - ptr.reach) * (1 - Math.exp(-dt / (ptr.treach > ptr.reach ? .6 : 1.2)));
    draw();
    raf = requestAnimationFrame(tick);
  };
  const start = () => {
    if (!prog) return;
    size();
    if (!follow) { clock = 6; reveal = 1; draw(); return; }
    last = performance.now();
    if (!raf) raf = requestAnimationFrame(tick);
  };

  // La palabra «Demeter» de fondo ocupa justo todo el ancho de la página.
  const big = stage.querySelector(".pl4__big");
  const fitBig = () => {
    if (!big) return;
    big.style.fontSize = "100px";
    const w = big.getBoundingClientRect().width;
    big.style.fontSize = ""; // vuelve al valor de --big
    if (w > 0) stage.style.setProperty("--big", `${(100 * document.documentElement.clientWidth / w).toFixed(1)}px`);
  };
  document.fonts?.ready.then(fitBig);

  // Al acabar de llegar corriendo y sentarse sobre la caja, Demetreo saluda (su clic dispara rebote y bocadillo).
  const av = stage.querySelector(".pl4__av");
  const onRun = (e) => { if (e.animationName === "pl4-svgin") av.click(); };
  av?.addEventListener("animationend", onRun);

  const onResize = () => { size(); if (!follow) draw(); fitBig(); };
  const onMove = (e) => { ptr.tx = e.clientX / innerWidth; ptr.ty = e.clientY / innerHeight; ptr.treach = 1; };
  const onLeave = () => { ptr.treach = 0; };
  addEventListener("resize", onResize);
  document.addEventListener("visibilitychange", start);
  if (follow) {
    addEventListener("pointermove", onMove, { passive: true });
    document.documentElement.addEventListener("pointerleave", onLeave);
  }
  start();
  fitBig();

  window.__loginFondoOff = () => {
    removeEventListener("resize", onResize);
    removeEventListener("pointermove", onMove);
    document.removeEventListener("visibilitychange", start);
    document.documentElement.removeEventListener("pointerleave", onLeave);
    av?.removeEventListener("animationend", onRun);
    cancelAnimationFrame(raf); raf = 0;
    window.__loginFondoOff = undefined;
  };
}
