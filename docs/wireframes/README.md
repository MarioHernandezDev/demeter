# Wireframes de Demeter (C1 · #28)

Bocetos de baja fidelidad de las 6 pantallas de la web app, en escritorio (1200 × 750) y
móvil (360 × 750). El gris marca huecos de contenido, los textos son los reales y los
círculos naranjas numerados se explican al pie de cada lámina.

Sirven para que el equipo apruebe **qué hay en cada pantalla, a dónde lleva cada botón y
qué datos pide a la API** antes de programarla. El aspecto final (foto de la costa,
letra condensada, colores) lo marca la portada; aquí solo se fija la estructura.

| # | Pantalla | Ruta | Acceso | Datos (tipos de `demeter/state/types.py`) | Issue que la construye |
|---|----------|------|--------|-------------------------------------------|------------------------|
| 01 | [Inicio (landing)](01-inicio.png) | `/` | pública | — (lectura de demo) | landing |
| 02 | [Iniciar sesión](02-login.png) | `/login` | pública | `LoginResponse`, `User` | C3 #30 |
| 03 | [Dashboard](03-dashboard.png) | `/dashboard` | sesión | `DashboardSummary` → `SensorSnapshot`, `Alert` | dashboard |
| 04 | [Parcela y sensor](04-parcela-sensor.png) | `/parcelas/[id]?sensor=` | sesión | `Parcel`, `Sensor`, `list[Reading]`, `HistoryQuery` | parcelas / gráficas |
| 05 | [Alertas](05-alertas.png) | `/alertas` | sesión | `list[Alert]` | alertas |
| 06 | [Umbrales y ajustes](06-ajustes.png) | `/ajustes` | sesión | `Sensor` (umbrales), `User` | umbrales |

## Navegación

```
/ (landing) ──«Ver el panel en vivo»──► /login ──entrar──► /dashboard
                    └─ con sesión ya iniciada ──────────────────┘
/dashboard ─ tarjeta de sensor ─► /parcelas/[id]?sensor=…
           ─ «Ver todas» ─► /alertas
cualquier página privada sin sesión ─► /login?next=<página> ─► vuelve a <página>
«Cerrar sesión» (barra lateral o /ajustes) ─► /login
```

- Escritorio: barra lateral fija (Dashboard, Parcelas, Alertas con contador, Ajustes;
  usuario y «Cerrar sesión» abajo).
- Móvil: barra superior con el estado «en directo» y pestañas abajo (Inicio, Parcelas,
  Alertas, Ajustes).
- `/parcelas` es una rejilla de tarjetas que lleva a la pantalla 04; con una sola
  parcela se salta directamente.

## Endpoints que usa cada pantalla

| Pantalla | Endpoint |
|----------|----------|
| 02 | `POST /api/auth/login` |
| 03 | `GET /api/dashboard` (cada 3 s, o `WS /ws/parcels/{id}` si se hace) |
| 04 | `GET /api/parcels`, `GET /api/parcels/{id}/sensors`, `GET /api/sensors/{id}/data?from=&to=&limit=` |
| 05 | `GET` de alertas y marcar como leída (**pendiente de acordar con la API**) |
| 06 | Guardar umbrales de un sensor (**pendiente de acordar con la API**) |

## Decisiones que hay que aprobar

1. **`/` es la landing pública.** La issue C2 (#29) decía que `/` redirige a `/login` o a
   `/dashboard`; con la landing, esa redirección pasa al botón «Ver el panel en vivo».
   Todas las demás páginas siguen protegidas.
2. **Dos roles:** `admin` edita umbrales; `tecnico` solo consulta.
3. **Usuario de demo para el jurado** (`tecnico`), creado por el seed.
4. **Faltan dos endpoints** en la lista del reto: marcar alerta como leída y guardar
   umbrales. Propuesta: `PATCH /api/alerts/{id}` y `PATCH /api/sensors/{id}`.

## Editar los bocetos

La fuente es [`fuente/wireframes.html`](fuente/wireframes.html) (un único HTML, sin
dependencias). Para regenerar los PNG:

```bash
pip install playwright && playwright install chromium
python docs/wireframes/fuente/capturar.py
```
