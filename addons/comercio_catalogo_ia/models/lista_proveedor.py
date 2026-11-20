import logging

from odoo import _, models
from odoo.addons.comercio_catalogo.catalogo.convertir import (
    _normalizar_titulo,
    _valores_numericos,
    filas_con_titulos,
    redetectar,
    titulos_de,
)
from odoo.exceptions import UserError

from ..ia import leer
from ..ia.verificar import ErrorIA
from .importacion import MAXIMO_POR_VEZ, _configuracion

_logger = logging.getLogger(__name__)
# Segundos para que la IA lea un PDF que también se puede leer del texto (si no, se usa el texto)
PLAZO_IA_PDF_CON_TEXTO = 120


class ComercioListaProveedor(models.Model):
    _inherit = "comercio.lista.proveedor"

    def _columnas_reconocibles(self, tabla):
        """¿Se puede leer la tabla del texto del PDF tal cual? Tiene que encontrar las columnas de la
        ficha (o, si no tiene, el costo y el código o la descripción), sin títulos repetidos y con
        precios que sean números. Si no, la lee la IA (20/11): un corralón sin títulos
        («HOLCIM X 25 KG; $6662», nombres en dos renglones), o un vivero con tres pares
        «DESCRIPCION | PRECIO» lado a lado que al leer el texto se mezclan («$ 2.700,00 LINEA IBIZA»)."""
        fila, costo = None, None
        if self.col_costo and (self.col_codigo or self.col_descripcion):
            fila = self.fila_encabezado or 1
            titulos = set(titulos_de(tabla, fila))
            elegidas = [t for t in (self.col_costo, self.col_codigo, self.col_descripcion) if t]
            if all(all(p.strip() in titulos for p in t.split(" + ")) for t in elegidas):
                costo = self.col_costo
        if not costo:
            detectado = redetectar(tabla)
            if not detectado:
                return False
            fila, mapeo = detectado
            costo = mapeo["costo"]
        encabezado = [_normalizar_titulo(c) for c in (tabla[fila - 1] if len(tabla) >= fila else []) if str(c).strip()]
        if len(encabezado) != len(set(encabezado)):
            return False  # «DESCRIPCION | PRECIO | DESCRIPCION | PRECIO»: productos lado a lado
        try:
            valores = _valores_numericos(filas_con_titulos(tabla, fila), costo)
        except ValueError:
            return False
        con_precio = [v for v in valores if v]
        return bool(valores) and len(con_precio) >= 0.8 * len(valores)

    def _tabla_de_documento(self, contenido, nombre_archivo):
        """Un PDF con texto se lee sin IA (módulo base), salvo que no se reconozcan sus columnas: ahí,
        igual que una foto o un PDF escaneado, lo transcribe Gemini; el resultado nunca se aplica
        solo. Si la IA no está o falla con un PDF con texto, queda la lectura del texto."""
        clave, modelos = _configuracion()
        try:
            resultado = super()._tabla_de_documento(contenido, nombre_archivo)
        except UserError:
            if not clave:
                raise
            resultado = None
        if resultado is not None:
            if not clave or self._columnas_reconocibles(resultado[0]):
                return resultado
            try:
                # Con plazo: si Google no anda, se sigue con la lectura del texto (no se frena)
                tabla, consumo, paginas = leer.leer(contenido, nombre_archivo, clave, modelos, productos=True,
                                                    plazo=PLAZO_IA_PDF_CON_TEXTO)
            except ErrorIA as error:
                _logger.warning("IA: no se pudo leer %s (sin columnas reconocibles): %s", nombre_archivo, error)
                return resultado
            return tabla, True, _(
                "El PDF tiene texto pero sin columnas reconocibles (sin títulos o en varios formatos): lo leyó "
                "la IA (%(modelo)s), %(p)s página(s), %(t)s tokens. Revisá contra el original: nada se aplica "
                "solo.", modelo=consumo.modelo, p=paginas, t=consumo.tokens)
        try:
            tabla, consumo, paginas = leer.leer(contenido, nombre_archivo, clave, modelos)
        except ErrorIA as error:
            raise UserError(_("No se pudo leer «%(n)s» con la IA: %(e)s", n=nombre_archivo, e=error)) from error
        _logger.info("IA: lista leída de %s (%s páginas, %s tokens, %s)", nombre_archivo, paginas,
                     consumo.tokens, consumo.modelo)
        return tabla, True, _(
            "Lista leída con IA (%(modelo)s) desde «%(n)s»: %(p)s página(s), %(t)s tokens. Revisá las subas "
            "y bajas grandes contra el original: nada se aplica solo.",
            modelo=consumo.modelo, n=nombre_archivo, p=paginas, t=consumo.tokens)

    def _importar_archivo(self, contenido, nombre_archivo, origen="manual", aplicar_seguros=False):
        """En las importaciones que se aplican solas (correo, enlace con «aplicar solo»), la IA revisa
        los posibles duplicados y productos nuevos y une sola lo que confirma con seguridad (ADR 0034).
        Si la IA no está o falla, la importación sigue igual: queda para una persona."""
        importacion = super()._importar_archivo(contenido, nombre_archivo, origen=origen,
                                                aplicar_seguros=aplicar_seguros)
        if aplicar_seguros and importacion.estado == "simulada" and not importacion.leida_con_ia \
                and _configuracion()[0]:
            filas = importacion.linea_ids.filtered(
                lambda li: not li.ia_veredicto and li._tipo_ia() in ("duplicado", "nuevo"))[:MAXIMO_POR_VEZ]
            if filas:
                try:
                    filas.action_verificar_ia()
                except UserError as error:
                    _logger.warning("IA al importar %s: %s", nombre_archivo, error)
        return importacion
