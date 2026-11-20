-- Usuarios de PostgreSQL del monitoreo (ADR 0028). Idempotente: se puede correr siempre.
-- Lo corren `make lab-monitoreo` y infra/servidor/configurar-monitoreo.sh (función
-- monitoreo_usuarios de infra/scripts/lib.sh), con las variables clave_monitoreo,
-- clave_lector y base.

SET client_min_messages = warning;

-- Consultas lentas (necesita shared_preload_libraries, compose.yml)
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- «monitoreo»: el exportador de Prometheus. pg_monitor = leer estadísticas, sin ver datos.
SELECT 'CREATE ROLE monitoreo LOGIN' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'monitoreo')
\gexec
ALTER ROLE monitoreo WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 3 PASSWORD :'clave_monitoreo';
GRANT pg_monitor TO monitoreo;
ALTER ROLE monitoreo SET statement_timeout = '20s';

-- «grafana_lector»: tableros del negocio. Solo lectura y solo las columnas que usan las
-- consultas de grafana/tableros/negocio.json (nada de mails, teléfonos ni direcciones).
SELECT 'CREATE ROLE grafana_lector LOGIN' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_lector')
\gexec
ALTER ROLE grafana_lector WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 5 PASSWORD :'clave_lector';
ALTER ROLE grafana_lector SET default_transaction_read_only = on;
ALTER ROLE grafana_lector SET statement_timeout = '30s';
GRANT CONNECT ON DATABASE :"base" TO grafana_lector;
GRANT USAGE ON SCHEMA public TO grafana_lector;

-- Columnas que puede leer (las que usan los tableros y las alertas del negocio). Se borra todo y
-- se vuelve a dar, así una columna que se deja de usar no queda abierta. Si un módulo no está
-- instalado, sus columnas se saltean. Agregar acá cada columna nueva que use una consulta.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM grafana_lector;
WITH pedidas (tabla, columnas) AS (VALUES
    ('pos_order', 'id,pos_reference,config_id,comercio_en_caja,state,date_order,amount_total,cashier'),
    ('pos_order_line', 'order_id,product_id,qty,price_subtotal_incl'),
    ('pos_config', 'id,name'),
    ('product_product', 'id,product_tmpl_id,default_code,barcode,active'),
    ('product_template', 'id,name,active,type,comercio_sin_codigo_fabrica,comercio_precio_desactualizado,comercio_precio_variacion,comercio_etiqueta_pendiente'),
    ('product_supplierinfo', 'id,partner_id,product_tmpl_id,product_code,price,date_start,date_end,comercio_escala_de_id'),
    ('res_company', 'id,comercio_diferencia_chica'),
    ('res_partner', 'id,name'),
    ('res_users', 'id,login,partner_id'),
    ('purchase_order', 'state,date_approve,amount_total,create_uid'),
    ('account_move', 'name,ref,partner_id,journal_id,move_type,state,date,invoice_date,create_date,create_uid,amount_total,payment_state,release_to_pay,comercio_total_factura'),
    ('account_journal', 'id,comercio_sin_factura'),
    ('stock_quant', 'product_id,location_id,quantity'),
    ('stock_location', 'id,usage,parent_path'),
    ('stock_move', 'product_id,location_id,location_dest_id,state,date,create_uid'),
    ('stock_warehouse_orderpoint', 'product_id,location_id,product_min_qty,active'),
    ('stock_picking', 'name,origin,partner_id,picking_type_id,state,scheduled_date,date_done,write_uid'),
    ('stock_picking_type', 'id,code'),
    ('comercio_lista_proveedor', 'id,name,parte,partner_id,frecuencia_dias,active,create_date'),
    ('comercio_lista_importacion', 'id,lista_id,estado,fecha,cant_revisar,create_date,create_uid')
)
SELECT format('GRANT SELECT (%s) ON public.%I TO grafana_lector',
              string_agg(quote_ident(c.column_name), ', '), p.tabla)
FROM pedidas p
CROSS JOIN LATERAL unnest(string_to_array(p.columnas, ',')) AS col (nombre)
JOIN information_schema.columns c
  ON c.table_schema = 'public' AND c.table_name = p.tabla AND c.column_name = col.nombre
GROUP BY p.tabla
\gexec

-- Por si quedó registrado algún comando con una clave (antes de track_utility=off, compose.yml)
\o /dev/null
SELECT pg_stat_statements_reset(userid, dbid, queryid) FROM pg_stat_statements WHERE query ~* 'password';
\o
