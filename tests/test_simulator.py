"""Pruebas del simulador (B4, issue #15). Ninguna usa la red ni espera de verdad."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from demeter.api.app import api
from demeter.db import repositorio
from demeter.db.seed import SENSORS, THRESHOLDS
from simulator import cliente
from simulator.__main__ import _opciones, crear_modelos, ejecutar
from simulator.cliente import Respuesta
from simulator.modelos import HumedadSuelo, Luminosidad, NivelDeposito, Temperatura

T0 = datetime(2026, 11, 24, 0, 0, tzinfo=timezone.utc)  # medianoche UTC
MINUTO = timedelta(minutes=1)
TIPO = {codigo: tipo for codigo, _finca, tipo, _desc in SENSORS}


def _serie(modelo, dias=1, paso=MINUTO, inicio=T0):
    """Los valores de un modelo durante ``dias``, con un paso por minuto: ``[(instante, valor)]``."""
    valores, instante = [], inicio
    for _ in range(int(dias * 24 * 60 * MINUTO / paso)):
        valores.append((instante, modelo.avanzar(instante, paso)))
        instante += paso
    return valores


# ---------------------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("semilla", [1, 2, 3])
def test_una_semana_normal_no_cruza_ningun_umbral_del_seed(semilla):
    """En funcionamiento normal no debe saltar ninguna alerta: eso queda para los escenarios."""
    for modelo in crear_modelos(semilla=semilla):
        bajo, alto = THRESHOLDS[TIPO[modelo.codigo]]
        for instante, valor in _serie(modelo, dias=7):
            assert bajo is None or valor >= bajo, (modelo.codigo, instante, valor)
            assert alto is None or valor <= alto, (modelo.codigo, instante, valor)


def test_la_temperatura_sube_por_la_tarde_y_baja_de_madrugada():
    serie = dict(_serie(Temperatura("t001", semilla=1)))
    assert serie[T0.replace(hour=15)] > serie[T0.replace(hour=4)] + 8


def test_la_luz_es_cero_de_noche_y_alta_a_mediodia():
    serie = dict(_serie(Luminosidad("l001", semilla=1)))
    assert serie[T0.replace(hour=2)] == 0 and serie[T0.replace(hour=22)] == 0
    assert serie[T0.replace(hour=12, minute=30)] > 40


def test_la_humedad_del_suelo_baja_y_se_riega_al_llegar_al_minimo():
    valores = [v for _, v in _serie(HumedadSuelo("h001", semilla=1), dias=5)]
    subidas = [b - a for a, b in zip(valores, valores[1:]) if b - a > 10]
    assert subidas, "debería haber al menos un riego en 5 días"
    assert min(valores) >= 30  # se riega antes de acercarse al umbral de 25


def test_sin_riego_la_humedad_del_suelo_cruza_el_umbral():
    # Lo que aprovechará el escenario "fallo de riego" (#16).
    modelo = HumedadSuelo("h001", semilla=1)
    modelo.riega = False
    assert min(v for _, v in _serie(modelo, dias=5)) < THRESHOLDS["humedad_suelo"][0]


def test_el_deposito_baja_y_se_rellena():
    valores = [v for _, v in _serie(NivelDeposito("d001", semilla=1), dias=15)]
    assert any(b - a > 30 for a, b in zip(valores, valores[1:])), "debería rellenarse"


def test_con_la_misma_semilla_sale_lo_mismo_y_con_otra_no():
    def serie(semilla):
        return [v for _, v in _serie(Temperatura("t001", semilla=semilla), dias=0.1)]

    assert serie(5) == serie(5)
    assert serie(5) != serie(6)


def test_dos_sensores_del_mismo_tipo_no_dan_lo_mismo():
    a, b = crear_modelos(["t001", "t002"], semilla=1)
    assert [v for _, v in _serie(a, dias=0.1)] != [v for _, v in _serie(b, dias=0.1)]


# ---------------------------------------------------------------------------------------
# Qué sensores se simulan
# ---------------------------------------------------------------------------------------


def test_por_defecto_simula_los_14_sensores_del_seed():
    assert [m.codigo for m in crear_modelos()] == [codigo for codigo, *_ in SENSORS]


def test_se_puede_elegir_sensores_y_salen_en_el_orden_del_seed():
    assert [m.codigo for m in crear_modelos(["h001", "t001"])] == ["t001", "h001"]


def test_un_sensor_que_no_es_del_seed_es_un_error():
    # Así un sensor real (p. ej. de una placa Arduino) nunca se simula, ni por una errata.
    with pytest.raises(ValueError, match="t101"):
        crear_modelos(["t001", "t101"])


# ---------------------------------------------------------------------------------------
# El bucle (con un "mandar" de mentira)
# ---------------------------------------------------------------------------------------


class _Api:
    """Hace de API: apunta lo que recibe y contesta lo que le digamos por sensor."""

    def __init__(self, respuestas=None):
        self.recibido: list[tuple[str, datetime, float]] = []
        self.respuestas = respuestas or {}

    def __call__(self, codigo, instante, valor):
        self.recibido.append((codigo, instante, valor))
        return self.respuestas.get(codigo, Respuesta(estado=200))


def _ejecutar(api_falsa, modelos=None, **kwargs):
    mensajes: list[str] = []
    salida = ejecutar(
        modelos or crear_modelos(["t001", "h001"], semilla=1), api_falsa,
        reloj=lambda: T0, dormir=lambda _s: None, avisar=mensajes.append, **kwargs,
    )
    return salida, mensajes


def test_cada_ronda_manda_una_lectura_por_sensor_con_la_hora_real():
    api_falsa = _Api()
    salida, mensajes = _ejecutar(api_falsa, rondas=3)
    assert salida == 0 and len(mensajes) == 3
    assert [c for c, _, _ in api_falsa.recibido] == ["t001", "h001"] * 3
    assert all(instante == T0 for _, instante, _ in api_falsa.recibido)


def test_la_velocidad_acelera_los_valores_pero_no_la_hora_enviada():
    # Con velocidad 60 y una ronda por minuto, cada ronda avanza una hora simulada. La hora que
    # se envía sigue siendo la real: la API rechaza horas de más de 5 min en el futuro.
    api_falsa = _Api()
    modelos = crear_modelos(["l001"], semilla=1)
    _ejecutar(api_falsa, modelos=modelos, rondas=13, intervalo=60, velocidad=60)
    valores = [v for _, _, v in api_falsa.recibido]
    assert valores[0] == 0  # medianoche simulada: noche
    assert valores[12] > 40  # doce rondas después son las 12:00 simuladas: pleno sol
    assert all(instante == T0 for _, instante, _ in api_falsa.recibido)


def test_espera_el_intervalo_descontando_lo_que_tarda_la_ronda():
    horas = iter([T0, T0, T0 + timedelta(seconds=5), T0, T0])
    esperas: list[float] = []
    ejecutar(
        crear_modelos(["t001"], semilla=1), _Api(), rondas=2, intervalo=60,
        reloj=lambda: next(horas), dormir=esperas.append, avisar=lambda _m: None,
    )
    assert esperas == [55.0]  # una sola espera (entre las dos rondas), de 60 - 5 s


def test_una_lectura_repetida_se_cuenta_pero_no_es_error():
    api_falsa = _Api({"t001": Respuesta(estado=200, repetida=True)})
    salida, mensajes = _ejecutar(api_falsa, rondas=1)
    assert salida == 0 and "1 repetidas" in mensajes[0]


def test_con_la_clave_incorrecta_para_enseguida():
    api_falsa = _Api({"t001": Respuesta(estado=401)})
    salida, mensajes = _ejecutar(api_falsa, rondas=5)
    assert salida == 2 and len(api_falsa.recibido) == 1
    assert "X-API-Key" in mensajes[-1]


def test_un_sensor_que_no_existe_en_la_api_se_deja_de_simular():
    api_falsa = _Api({"t001": Respuesta(estado=404)})
    salida, _ = _ejecutar(api_falsa, rondas=3)
    assert salida == 0
    assert [c for c, _, _ in api_falsa.recibido] == ["t001", "h001", "h001", "h001"]


def test_si_no_queda_ningun_sensor_termina():
    api_falsa = _Api({"t001": Respuesta(estado=404), "h001": Respuesta(estado=404)})
    salida, mensajes = _ejecutar(api_falsa, rondas=0)  # 0 = sin fin, pero no queda nada
    assert salida == 1 and "ningún sensor" in mensajes[-1]


def test_con_la_api_apagada_avisa_y_sigue_intentandolo():
    apagada = Respuesta(estado=None, detalle="Connection refused")
    api_falsa = _Api({"t001": apagada, "h001": apagada})
    salida, mensajes = _ejecutar(api_falsa, rondas=3)
    assert salida == 0 and len(api_falsa.recibido) == 6  # lo intenta las tres rondas
    assert all("Connection refused" in m for m in mensajes)


# ---------------------------------------------------------------------------------------
# Opciones de la línea de órdenes
# ---------------------------------------------------------------------------------------


def test_rapido_es_un_atajo_de_intervalo_y_velocidad():
    opciones = _opciones(["--rapido"])
    assert (opciones.intervalo, opciones.velocidad) == (2.0, 60.0)


@pytest.mark.parametrize("args", [["--intervalo", "0"], ["--velocidad", "-1"], ["--rondas", "-2"]])
def test_opciones_imposibles_se_rechazan(args):
    with pytest.raises(SystemExit):
        _opciones(args)


def test_la_clave_y_la_url_salen_del_entorno(monkeypatch):
    monkeypatch.setenv("DEMETER_INGEST_KEY", "otra-clave")
    monkeypatch.setenv("DEMETER_API_URL", "http://api:8000")
    opciones = _opciones([])
    assert (opciones.api_key, opciones.api_url) == ("otra-clave", "http://api:8000")


# ---------------------------------------------------------------------------------------
# De punta a punta: el simulador contra la API de verdad (en memoria, sin red)
# ---------------------------------------------------------------------------------------


@pytest.mark.usefixtures("api_db")
def test_contra_la_api_guarda_las_lecturas_y_no_abre_alertas():
    http = TestClient(api)

    def mandar(codigo, instante, valor):
        # Lo mismo que hace ``cliente.enviar``, pero por el cliente de pruebas de FastAPI.
        r = http.post(
            f"/api/sensors/{codigo}/data",
            json={"timestamp": instante.isoformat(), "value": valor},
            headers={"X-API-Key": "demo-ingest-key"},
        )
        return Respuesta(estado=r.status_code, repetida=r.json().get("duplicate", False))

    ahora = datetime.now(timezone.utc)
    horas = iter(ahora + timedelta(seconds=i) for i in range(100))
    salida = ejecutar(
        crear_modelos(semilla=1), mandar, rondas=3,
        reloj=lambda: next(horas), dormir=lambda _s: None, avisar=lambda _m: None,
    )
    assert salida == 0
    assert len(repositorio.readings("t001")) == 3
    assert set(repositorio.last_readings(1)) == {"t001", "h001", "l001", "a001", "d001"}
    assert repositorio.list_alerts()[1] == 0  # valores normales: ninguna alerta
    (deposito,) = repositorio.tanks(1)
    assert deposito.level_pct is not None  # el depósito ya sabe cuánta agua tiene


# ---------------------------------------------------------------------------------------
# cliente.enviar
# ---------------------------------------------------------------------------------------


def test_enviar_sin_api_no_lanza_excepcion():
    # Puerto 9 ("discard"): nadie escucha, la conexión se rechaza al momento.
    respuesta = cliente.enviar("http://127.0.0.1:9", "k", "t001", T0, 1.0, timeout=1)
    assert respuesta.estado is None and not respuesta.ok
