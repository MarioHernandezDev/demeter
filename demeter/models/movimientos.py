"""Modelo de la tabla ``transactions`` (docs/modelo-datos.md, sección 4.4)."""

from datetime import date

from sqlmodel import Field, SQLModel


class Transaction(SQLModel, table=True):
    """Coste o ingreso de una parcela."""

    __tablename__ = "transactions"

    id: int | None = Field(default=None, primary_key=True)
    parcel_id: int = Field(foreign_key="parcels.id", index=True)

    # ``income`` (ingreso) | ``expense`` (gasto). Se valida en la aplicación.
    kind: str

    # Concepto: agua, abono, venta...
    category: str

    # Importe en euros, SIEMPRE positivo (decisión 21): el signo lo da ``kind``.
    # Es ``float`` porque así lo define la API (schemas.py) y porque SQLite no
    # tiene decimales exactos. Al sumar importes, redondear a 2 decimales en
    # el código que los sume (repositorio, #13).
    amount: float

    # Solo el día, sin hora: un gasto se anota por fecha, y no hay zona
    # horaria que confundir.
    occurred_on: date

    # Nota libre, opcional.
    description: str | None = Field(default=None)