"""Simulador de sensores (B4, issue #15).

Hace de las placas que todavía no tenemos: cada cierto tiempo inventa una lectura realista para
cada sensor del seed y la manda a la API (``POST /api/sensors/{id}/data`` con ``X-API-Key``),
exactamente igual que lo hará una placa Arduino. Así las lecturas pasan por la ingesta y por el
motor de alertas, y el dashboard se mueve solo.

Se divide en tres partes, cada una en su fichero:

- ``modelos``: cómo cambia cada magnitud (ciclo del día, riegos, ruido). No sabe nada de HTTP.
- ``cliente``: cómo se manda una lectura a la API. No sabe nada de valores.
- ``__main__``: el bucle que junta las dos y las opciones de la línea de órdenes.

Uso (con la API arrancada):

    python -m simulator                 # una lectura por sensor cada minuto, en tiempo real
    python -m simulator --rapido        # demo: cada 2 s, y un día entero pasa en 24 min
    python -m simulator --help          # todas las opciones
"""
