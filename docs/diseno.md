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

Todos los textos cumplen WCAG AA (4,5:1).

## Tipografía

- **Mona Sans** (variable, ancho 75–125): interfaz. El nombre «DEMETER» de la portada va en ancho 75 %.
- **Instrument Serif** cursiva: acentos en titulares («*uno pide agua.*»). **DM Serif Display**: el nombre del pie.
- **Geist Mono**: cifras de sensores, etiquetas y fechas.

Se cargan desde Google Fonts (`theme.GOOGLE_FONTS`); si no hay red, caen a las fuentes del sistema.

## Cómo está montado

| Pieza | Dónde | Qué hace |
|---|---|---|
| Barra y pestañas | `demeter/components/layout.py` (Reflex) | Sección activa con `aria-current`, alertas sin leer (`UIState`), usuario y «Salir» (`AuthState`). Tres variantes: `app`, `portada` y `acceso`. En móvil (≤ 760 px) la navegación pasa a una píldora de cuatro pestañas abajo. |
| Login | `demeter/pages/login.py` (Reflex) | Formulario con el diseño del prototipo que ya envía a `AuthState.login` (C3 #30 lo conecta a la API). |
| Contenido de cada pantalla | `demeter/pages/plantillas/*.html` | Maqueta del prototipo con datos de ejemplo, insertada con `prototipo.contenido()`. |
| Estilos, scripts e imágenes | `assets/proto/` | `proto.css`, `app.css` y `mascota.css`; `intro.js` (portada: niebla y bancal en líneas con Three.js), `twin.js` (gemelo 3D del panel), `app.js` (gráficas, mapa, alertas y umbrales de ejemplo) y `mascota.js` (Demetreo griego: pie, aviso y 404). |

**Cómo se sustituye una plantilla:** la rama de cada pantalla (por ejemplo `feature/dashboard-graficas` en el panel) rehace su contenido con componentes Reflex y datos de la API, borra su `.html` de `plantillas/` y deja de llamar a `prototipo.contenido()`. La barra y las pestañas no se tocan.

`intro.js` y `twin.js` llevan Three.js dentro cada uno (≈ 540 kB). Se puede sacar a un archivo común más adelante si pesa en la demo.

## Rutas

| Ruta | Acceso | Qué es |
|---|---|---|
| `/` | pública | portada. «Ver el panel en vivo» → `/dashboard` con sesión, `/login?next=/dashboard` sin ella |
| `/login` | pública | acceso (lo conecta a la API C3 #30) |
| `/dashboard`, `/parcelas`, `/alertas`, `/ajustes` | con sesión | panel con gemelo 3D, parcelas con mapa, alertas y umbrales |
| cualquier otra | pública | 404 con Demetreo |
