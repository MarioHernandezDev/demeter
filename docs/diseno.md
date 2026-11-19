# Diseño · paleta, tipografía y layout (C2, #29)

Todo sale de `demeter/theme.py`. Las páginas usan las variables CSS `--dm-*`; si cambia la paleta, se cambia allí y aquí, en ningún otro sitio. La paleta es la del prototipo de la portada y puede cambiar más adelante.

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

- **Mona Sans** (variable, ancho 75–125): interfaz. La marca «DEMETER» va en 800 y ancho 75 %.
- **Instrument Serif** cursiva: solo acentos en titulares («*en tiempo real*»).
- **Geist Mono**: cifras de sensores, etiquetas y fechas.

Se cargan desde Google Fonts (`theme.GOOGLE_FONTS`); si no hay red, caen a las fuentes del sistema.

## Layout

- `layout(*contenido, activa="/ruta", publica=False)` en `demeter/components/layout.py`.
- **Escritorio:** barra superior fija con la marca, Panel · Parcelas · Alertas · Ajustes, la burbuja de alertas sin leer (`UIState.alertas_sin_leer`) y el usuario con «Salir».
- **Móvil (≤ 760 px):** la navegación pasa a cuatro pestañas fijas abajo, con icono y texto, respetando la zona segura del iPhone. Es solo CSS: no hay estado que sincronizar.
- **Públicas** (`/` y `/login`): misma marca, sin navegación de la app.
- La sección activa lleva `aria-current="page"`.

## Rutas

| Ruta | Acceso | Qué es |
|---|---|---|
| `/` | pública | portada. «Ver el panel en vivo» → `/dashboard` con sesión, `/login?next=/dashboard` sin ella |
| `/login` | pública | formulario (lo conecta a la API C3 #30) |
| `/dashboard`, `/parcelas`, `/alertas`, `/ajustes` | con sesión | marco listo; cada hueco indica la rama que lo completa |
