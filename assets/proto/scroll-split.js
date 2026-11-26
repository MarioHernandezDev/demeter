// Gemelo 3D en la portada: un bancal en terrazas (Three.js) dentro de una tarjeta que, al bajar,
// se parte en tres paneles y se da la vuelta para enseñar qué hace Demeter (medir, avisar, regar).
// three.js 0.160.0 (MIT) va copiado en assets/proto/vendor: la demo tiene que funcionar sin internet.
import * as THREE from './vendor/three.module.min.js';

window.__ssCleanup?.();
const root = document.querySelector('.ss');
const card = root?.querySelector('[data-ss-card]');
if (root && card) {
  const panels = [...card.querySelectorAll('[data-ss-panel]')];
  const slices = [...card.querySelectorAll('[data-ss-slice]')];
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ---- escena: 4 terrazas escalonadas con hileras de cultivo y sensores
  let W = 960, H = 540;
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xbfd2c3);
  scene.fog = new THREE.Fog(0xbfd2c3, 9, 20);
  const cam = new THREE.PerspectiveCamera(32, W / H, 0.1, 50);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x6b7f5e, 1.1));
  const sun = new THREE.DirectionalLight(0xfff1d6, 2.2);
  sun.position.set(4, 8, 5);
  scene.add(sun);

  const model = new THREE.Group();
  scene.add(model);
  const soil = new THREE.MeshStandardMaterial({ color: 0x9a7b55, roughness: 1 });
  const grass = new THREE.MeshStandardMaterial({ color: 0x6f9a4e, roughness: 1 });
  const crop = new THREE.MeshStandardMaterial({ color: 0x2f6b3a, roughness: 0.9 });
  const post = new THREE.MeshStandardMaterial({ color: 0xdedede });
  const blips = [];
  for (let i = 0; i < 4; i++) {
    const w = 6.4 - i * 1.05, d = 3.2 - i * 0.3, y = i * 0.62, z0 = -i * 0.55;
    const base = new THREE.Mesh(new THREE.BoxGeometry(w, 0.62, d), soil);
    base.position.set(0, y + 0.31 - 1, z0);
    const top = new THREE.Mesh(new THREE.BoxGeometry(w, 0.08, d), grass);
    top.position.set(0, y + 0.66 - 1, z0);
    model.add(base, top);
    const rows = 3 + (i % 2), cols = Math.floor(w * 2.4);
    for (let r = 0; r < rows; r++) {
      const z = z0 - d / 2 + 0.5 + r * ((d - 1) / (rows - 1));
      for (let c = 0; c < cols; c++) {
        const bush = new THREE.Mesh(new THREE.ConeGeometry(0.11, 0.22, 6), crop);
        bush.position.set(-w / 2 + 0.3 + c * ((w - 0.6) / (cols - 1)), y + 0.81 - 1, z);
        model.add(bush);
      }
    }
    const stick = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.5), post);
    stick.position.set(w / 2 - 0.5, y + 0.95 - 1, z0 + d / 2 - 0.35);
    const blip = new THREE.Mesh(
      new THREE.SphereGeometry(0.09, 16, 12),
      new THREE.MeshBasicMaterial({ color: i === 2 ? 0xff5a36 : 0x35d07f }),
    );
    blip.position.set(stick.position.x, stick.position.y + 0.3, stick.position.z);
    model.add(stick, blip);
    blips.push(blip);
  }

  // ---- las tres franjas copian cada una su tercio del canvas de WebGL
  const ctxs = slices.map((c) => c.getContext('2d'));
  // Resolución real de pantalla (×DPR, tope 2): el canvas ocupa toda la ventana y se ve nítido.
  const resize = () => {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    W = Math.max(3, Math.round(innerWidth * dpr));
    H = Math.max(3, Math.round(innerHeight * dpr));
    renderer.setSize(W, H, false);
    cam.aspect = W / H;
    cam.fov = cam.aspect < 0.9 ? 52 : 32;
    cam.updateProjectionMatrix();
    slices.forEach((c) => { c.width = Math.round(W / 3); c.height = H; });
    ctxs.forEach((x) => { x.imageSmoothingEnabled = false; });
  };
  resize();

  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const ease = (t) => 1 - Math.pow(1 - t, 3);
  let p = 0, target = 0, raf = 0;

  const measure = () => {
    const r = root.getBoundingClientRect();
    const run = r.height - innerHeight;
    target = run > 0 ? clamp(-r.top / run) : 1;
  };
  const apply = () => {
    // 0–.2 pantalla completa (el modelo gira) · .2–.4 se parte · .42–.9 cada panel se da la vuelta
    const split = ease(clamp((p - 0.2) / 0.2));
    card.style.setProperty('--split', split.toFixed(3));
    root.style.setProperty('--ss', p.toFixed(3));
    panels.forEach((el, i) => {
      const f = ease(clamp((p - 0.42 - i * 0.1) / 0.3));
      el.style.setProperty('--flip', f.toFixed(3));
      el.style.setProperty('--lift', (split * (1 - f)).toFixed(3));
    });
  };

  const frame = (t) => {
    raf = requestAnimationFrame(frame);
    p += (target - p) * 0.2;
    const ang = 0.55 + p * 1.9 + (reduced ? 0 : t * 0.00008);
    cam.position.set(Math.sin(ang) * 11, 5.2 - p * 1.4, Math.cos(ang) * 11);
    cam.lookAt(0, 0.5, -0.9);
    blips.forEach((b, i) => b.scale.setScalar(1 + 0.35 * Math.sin(t * 0.004 + i * 1.7)));
    renderer.render(scene, cam);
    const sw = Math.round(W / 3);
    ctxs.forEach((x, i) => x.drawImage(renderer.domElement, i * sw, 0, sw, H, 0, 0, sw, H));
    apply();
  };

  addEventListener('scroll', measure, { passive: true });
  addEventListener('resize', measure);
  addEventListener('resize', resize);
  measure();
  raf = requestAnimationFrame(frame);

  // ---- «páginas»: entre la cabina, el gemelo y lo que sigue no se puede quedar a medias.
  // Si estás entre dos pantallas, al deslizar te lleva entera a la siguiente (o a la anterior).
  const cockpit = document.querySelector('[data-cab3]');
  const next = document.querySelector('.next');
  const pages = [cockpit, root, next].filter(Boolean);
  const topOf = (el) => el.getBoundingClientRect().top + scrollY;
  const maxY = () => document.documentElement.scrollHeight - innerHeight;
  let lastY = scrollY, tween = 0, locked = false;
  const goTo = (to) => {
    cancelAnimationFrame(tween);
    const from = scrollY, dist = to - from;
    if (reduced || Math.abs(dist) < 2) { scrollTo(0, to); return; }
    locked = true;
    const dur = Math.min(900, 420 + Math.abs(dist) * 0.25), t0 = performance.now();
    const step = (now) => {
      const k = Math.min(1, (now - t0) / dur);
      scrollTo(0, from + dist * (1 - Math.pow(1 - k, 4)));
      if (k < 1) tween = requestAnimationFrame(step);
      else setTimeout(() => { locked = false; lastY = scrollY; }, 60);
    };
    tween = requestAnimationFrame(step);
  };
  const snap = () => {
    const y = scrollY, down = y > lastY;
    lastY = y;
    if (locked) return;
    for (let i = 1; i < pages.length; i++) {
      const end = Math.min(topOf(pages[i]), maxY()), start = topOf(pages[i]) - innerHeight;
      if (y > start + 4 && y < end - 4) { goTo(down ? end : Math.max(0, start)); return; }
    }
  };
  const stopWheel = (e) => { if (locked) e.preventDefault(); };
  addEventListener('scroll', snap, { passive: true });
  addEventListener('wheel', stopWheel, { passive: false });

  window.__ssCleanup = () => {
    cancelAnimationFrame(tween);
    removeEventListener('scroll', snap);
    removeEventListener('wheel', stopWheel);
    cancelAnimationFrame(raf);
    removeEventListener('scroll', measure);
    removeEventListener('resize', measure);
    removeEventListener('resize', resize);
    renderer.dispose();
  };
}
