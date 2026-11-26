# Diseño · paleta, tipografía y layout (C2, #29)

La web reproduce el prototipo **«Demeter web completa con Demetreo griego»**. La paleta vive en `demeter/theme.py` (variables `--dm-*` para el código Reflex nuevo) y coincide con la de las hojas del prototipo en `assets/proto/`; una prueba (`test_la_paleta_coincide_con_la_del_prototipo`) avisa si se separan.

## Paleta

| Token | Valor | Uso | Contraste sobre `papel` |
|---|---|---|---|
| `tinta` | `#12181a` | texto principal, pestañas en móvil | 15,4:1 |
| `tinta_suave` | `#56626a` | texto secundario, etiquetas | 5,4:1 |
| `papel` | `#eceeed` | fondo | — |
| `papel_2` | `#e3e6e5` | tarjetas | — |
| `acento` | `#b33a12` | botones, enlaces, alertas | 5,1:1 (texto blanco encima: 5,9:1) |
| `ok` | `#2f8a63` | **solo** puntos de estado | 3,7:1 (no apto para texto) |
| `ok_texto` | `#1f6b4c` | texto «en rango» | 5,5:1 |
| `campo` | `#3e5a22` | fondos de marca (Demetreo) | — |
| `sin_senal` | `#8a9499` | **solo** punto, borde y mini histórico de un sensor sin señal | 2,7:1 (no apto para texto) |

Todos los textos cumplen WCAG AA (4,5:1).

## Semáforo de las tarjetas de sensor

Lo manda la API en `sensors[].status` (`GET /api/dashboard`). La tabla vive en `theme.ESTADOS_SENSOR`; las clases, en `assets/proto/app.css`.

| `status` | Etiqueta | Clase | Aspecto |
|---|---|---|---|
| `ok` | En rango | — | punto verde |
| `LOW` / `HIGH` | Bajo / Alto | `srow--warn` · `ro is-warn` | cifra y gráfica en terracota |
| `offline` | Sin señal | `srow--off` · `ro is-off` | tarjeta gris: cifra apagada en `tinta_suave`, gráfica discontinua en `sin_senal`. Gana a «bajo»/«alto» |
| `sin_datos` | Esperando datos | `srow--wait` | sin cifra ni alarma |

`offline` solo puede venir del servidor (necesita la hora de la última lectura): `Sensor.status_for` nunca lo devuelve.

## Modo oscuro

El estado es el modo de color de Reflex: clase `dark` en `<html>` y `localStorage.theme` (el script que Reflex pone en el `<head>` lo aplica antes de pintar, así que no hay parpadeo). El botón sol/luna está en las tres barras (`tema.boton_tema()`).

- **Paleta:** `assets/proto/tema.css` redefine en `html.dark` las variables del prototipo (`--ink`, `--paper`, `--muted`, `--warn`, `--off`…) y las `--dm-*`. Los botones que en claro son tinta con texto blanco pasan a ser claros con texto tinta. La cabina de la portada y las fotos no cambian; la foto de la portada se oscurece y el gemelo del panel se invierte.
- **Cambio animado:** `assets/proto/tema.js`. Una mancha de tinta sale del botón y se extiende en vetas y humo (campo de ruido en WebGL2 + View Transitions + filtro SVG). Sin View Transitions, sin WebGL2 o con «reducir movimiento», el cambio es instantáneo.

| Token oscuro | Valor | Uso | Contraste sobre `#0e1315` |
|---|---|---|---|
| `--ink` / `--dm-tinta` | `#e6ebe9` | texto principal | 15,5:1 |
| `--muted` / `--dm-tinta-suave` | `#95a3a9` | texto secundario | 7,2:1 |
| `--paper` / `--dm-papel` | `#0e1315` | fondo | — |
| `--warn` / `--dm-acento` | `#f07a45` | alertas y acento | 6,7:1 |
| `--dm-ok-texto` | `#5cc795` | texto «en rango» | 9,0:1 |
| `--off` / `--dm-sin-senal` | `#7d8b91` | **solo** punto, borde y mini histórico sin señal | 5,3:1 |

## Tipografía

- **Mona Sans** (variable, ancho 75–125): interfaz. El nombre «DEMETER» de la portada va en ancho 75 %.
- **Instrument Serif** cursiva: acentos en titulares («*uno pide agua.*»). **DM Serif Display**: el nombre del pie.
- **Geist Mono**: cifras de sensores, etiquetas y fechas.

Se cargan desde Google Fonts (`theme.GOOGLE_FONTS`); si no hay red, caen a las fuentes del sistema.

## Cómo está montado

| Pieza | Dónde | Qué hace |
|---|---|---|
| Barra y pestañas | `demeter/components/layout.py` (Reflex) | Sección activa con `aria-current`, alertas sin leer (`UIState`), usuario y «Salir» (`AuthState`). Tres variantes: `app`, `portada` y `acceso`. En móvil (≤ 760 px) la navegación pasa a una píldora de cuatro pestañas abajo. |
| Login | `demeter/pages/login.py` (Reflex) + `assets/login/` | Variante «Aurora» del prototipo de login: fondo WebGL (`fondo.js`), caja de cristal y Demetreo, que llega corriendo, sigue el usuario con los ojos y se tapa los ojos con la contraseña (`demetreo.js`). El formulario envía a `AuthState.login` (C3 #30 lo conecta a la API). |
| Contenido de cada pantalla | `demeter/pages/plantillas/*.html` | Maqueta del prototipo con datos de ejemplo, insertada con `prototipo.contenido()`. |
| Modo oscuro | `demeter/components/tema.py` + `assets/proto/tema.css` y `tema.js` | Botón sol/luna de la barra y lo que va en el `<head>` de todas las páginas (`tema.cabeza()`, desde `demeter/demeter.py`). |
| Estilos, scripts e imágenes | `assets/proto/` | `proto.css`, `app.css` y `mascota.css`; `intro.js` (portada: niebla y bancal en líneas con Three.js), `twin.js` (gemelo 3D del panel), `app.js` (gráficas, mapa, alertas y umbrales de ejemplo) y `mascota.js` (Demetreo griego: pie, aviso y 404). |
| Cabina de los mundos (portada) | `demeter/components/cabina3d.py` + `assets/cabina3d/cabina3d.jsx` | Componente React con three.js (dependencia npm, va empaquetada). Cabina de nave que gira con una ventana por mundo, paralaje por profundidad y postprocesado (dithering, grano, viñeta). Datos en `assets/proto/cabina/mundos.json`. Sin WebGL, si la escena falla o con «reducir movimiento», usa la versión CSS de `assets/proto/cabina/` (GSAP desde cdnjs). Se mete en `inicio.html` con `prototipo.contenido_con_centro()` en el marcador `@mundos`. |
| Gemelo con scroll (portada) | `assets/proto/scroll-split.js` + `.ss` en `proto.css` | Bancal en terrazas con three.js (copiado en `assets/proto/vendor/`, sin CDN) que al bajar se parte en tres paneles y se dan la vuelta: medir, avisar y regar. Se pausa fuera de pantalla. |
| Cambio de página | `proto.css` (`dm-enter`) | Cada pantalla entra desenfocada y se enfoca en 0,55 s. |

**Cómo se sustituye una plantilla:** la rama de cada pantalla (por ejemplo `feature/dashboard-graficas` en el panel) rehace su contenido con componentes Reflex y datos de la API, borra su `.html` de `plantillas/` y deja de llamar a `prototipo.contenido()`. La barra y las pestañas no se tocan.

`intro.js` y `twin.js` llevan Three.js dentro cada uno (≈ 540 kB). Se puede sacar a un archivo común más adelante si pesa en la demo.

## Rutas

| Ruta | Acceso | Qué es |
|---|---|---|
| `/` | pública | portada. «Ver el panel en vivo» → `/dashboard` con sesión, `/login?next=/dashboard` sin ella |
| `/login` | pública | acceso (lo conecta a la API C3 #30) |
| `/dashboard`, `/parcelas`, `/alertas`, `/ajustes` | con sesión | panel con gemelo 3D, parcelas con mapa, alertas y umbrales |
| cualquier otra | pública | 404 con Demetreo |
