"""Del precio de la lista al costo (30/10): «IVA incluido (%)» pasa a «La lista trae el IVA
incluido» más «IVA si no se sabe», y una cotización cargada marca la lista en dólares (con esa
cotización fija, como estaba). La columna vieja queda en la base sin usar."""


def migrate(cr, version):
    cr.execute("""SELECT 1 FROM information_schema.columns
                  WHERE table_name = 'comercio_lista_proveedor' AND column_name = 'iva_incluido'""")
    if cr.fetchone():
        cr.execute("""UPDATE comercio_lista_proveedor SET trae_iva = TRUE, iva_por_defecto = iva_incluido
                      WHERE iva_incluido > 0""")
    cr.execute("UPDATE comercio_lista_proveedor SET moneda = 'usd' WHERE cotizacion > 0")
