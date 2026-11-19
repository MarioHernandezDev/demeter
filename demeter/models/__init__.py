"""Modelos de la base de datos.

Hay que importar aquí todas las tablas: ``reflex db makemigrations`` solo
detecta las que están importadas, y una tabla sin importar se queda fuera
de las migraciones sin avisar.
"""

from .alertas import Alert  # noqa: F401
from .lecturas import SensorData  # noqa: F401
from .movimientos import Transaction  # noqa: F401
from .parcelas import Parcel  # noqa: F401
from .sensores import Sensor  # noqa: F401
from .terreno import Tank, TerrainElement, Zone  # noqa: F401
from .usuarios import User  # noqa: F401