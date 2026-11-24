# Relieve fino MDT02 (2 m)

Deja aquí los ficheros **GeoTIFF del MDT02 – 2ª cobertura** del CNIG (`MDT02-ETRS89-HU30-....-COB2.tif`).
El detector los usa solo si cubren la parcela: si no hay, sigue con el MDT de 5 m del servicio web.

## Cómo descargarlos

1. Entra en el **Centro de Descargas del CNIG**: https://centrodedescargas.cnig.es
2. Ve a **Modelos digitales de elevaciones → MDT02 – 2ª cobertura (2015–2021)**.
3. Busca la zona: escribe «Motril» o usa el visor y selecciona las **hojas MTN25** que cubren las parcelas.

   Las parcelas etiquetadas hasta ahora están todas en un radio de unos 2 km al norte de Motril:

   | Ejemplo | Lat | Lon |
   |---|---|---|
   | 57c555 | 36.76787 | -3.54085 |
   | 7eb33e | 36.76817 | -3.53650 |
   | 1d82d4 | 36.77005 | -3.53668 |
   | e8261b | 36.75845 | -3.52480 |
   | 271068 | 36.76632 | -3.54192 |

4. Añade los ficheros a la cesta, descárgalos y **copia los `.tif` en esta carpeta** (`demo/gemelo/mdt02/`).
   Usa el huso **30** (`HU30`). Si la descarga viene en `.zip`, descomprímela aquí.

Licencia: compatible con CC BY 4.0. Hay que citar «MDT02 cedido por © Instituto Geográfico Nacional».
Los `.tif` no se suben a git porque son grandes.

## Comprobar que se leen

```powershell
python -c "import sys; sys.path.insert(0,'demo/gemelo'); import mdt_fino; print(mdt_fino.hojas()); print(mdt_fino.cargar(452000,4068800,452300,4069100) is not None)"
```

Si Pillow no puede leer los ficheros (compresión no soportada), instala `tifffile`:

```powershell
pip install tifffile imagecodecs
```
