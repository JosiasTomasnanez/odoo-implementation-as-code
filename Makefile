# Atajos del proyecto. `make help` lista los objetivos.
ENV ?= lab
PY  ?= .venv/bin/python
IAC  = $(PY) -m odoo_iac
# VALORES=archivo.yaml suma un archivo de valores extra (demo, prueba rápida; ADR 0010)
VALORES ?=
VALORES_ARG = $(if $(VALORES),--valores $(VALORES))

.PHONY: web-proximamente web-tienda-demo web-tienda-dev tienda-admin tienda-respaldo help setup test lint ping plan apply verify e2e-pos e2e-catalogo e2e-precios e2e-codigos-fabrica e2e-tienda-sync e2e-tienda-cuentas e2e-tienda-admin e2e-tienda-panel e2e-tienda-pedidos e2e-tienda-cancelar e2e-ia e2e-factura e2e-factura-proveedor lab-arca lab-arca-cortar lab-arca-volver \
        lab-init lab-completo lab-lista-ejemplo lab-listas-reales lab-copia-prod lab-copia-prod-borrar lab-up lab-red lab-local lab-down lab-destroy lab-logs lab-shell backup restore-test \
        lab-monitoreo lab-monitoreo-down verify-monitoreo tableros

help: ## Mostrar esta ayuda
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

setup: ## Crear el entorno Python (.venv) con la herramienta y dependencias de desarrollo
	python3 -m venv .venv
	$(PY) -m pip install -q -e '.[dev]'

test: ## Correr los tests
	$(PY) -m pytest -q

e2e-pos: ## Prueba de punta a punta del puesto, las dos cajas con QR, la balanza Systel, el cobro en la registradora y la venta con y sin factura en el lab (requiere Playwright)
	.venv/bin/python tests/e2e/pos_pedido_qr.py
	.venv/bin/python tests/e2e/pos_escaneo_producto.py
	.venv/bin/python tests/e2e/pos_precio_en_vivo.py
	.venv/bin/python tests/e2e/pos_busqueda.py
	.venv/bin/python tests/e2e/pos_cierre.py
	.venv/bin/python tests/e2e/pos_dos_cajas.py
	.venv/bin/python tests/e2e/pos_balanza_systel.py
	.venv/bin/python tests/e2e/pos_cobro_registradora.py
	.venv/bin/python tests/e2e/pos_factura.py


e2e-catalogo: ## Prueba de punta a punta de las listas de proveedores (módulo comercio_catalogo) en el lab
	.venv/bin/python tests/e2e/catalogo_listas.py
	.venv/bin/python tests/e2e/compras_lista_vigente.py

e2e-ia: ## Verificación con IA de las listas, categorías del POS y foto del cierre Z (llama a Gemini de verdad; requiere GEMINI_API_KEY en .env)
	.venv/bin/python tests/e2e/catalogo_ia.py
	.venv/bin/python tests/e2e/pos_categorias_ia.py
	.venv/bin/python tests/e2e/cierre_z_foto.py

e2e-precios: ## Prueba de punta a punta de los precios de venta por margen (módulo comercio_precios) en el lab
	.venv/bin/python tests/e2e/precios.py
	.venv/bin/python tests/e2e/margen_proveedor.py

e2e-tienda-pedidos: ## Tienda online: compra con pago simulado → pedido confirmado en Odoo; última unidad a la vez; rechazo (fase 3)
	.venv/bin/python tests/e2e/tienda_pedidos.py

e2e-tienda-panel: ## Tienda online: panel de pedidos (alta del equipo, PIN, preparar → listo con la entrega en Odoo → retirado; fase 4)
	.venv/bin/python tests/e2e/tienda_panel.py

e2e-tienda-cancelar: ## Tienda online: cancelar un pedido desde la administración (arrepentimiento) → cancelado o devolución en Odoo
	.venv/bin/python tests/e2e/tienda_cancelar.py

e2e-tienda-admin: ## Tienda online: administración (equipo con roles, aprobar mayoristas → contacto en Odoo, listas para clientes; fase 7)
	.venv/bin/python tests/e2e/tienda_admin.py

e2e-tienda-cuentas: ## Tienda online: cuentas de clientes (código por mail, mis pedidos, pedido de cuenta mayorista; fase 6)
	.venv/bin/python tests/e2e/tienda_cuentas.py

e2e-tienda-sync: ## Tienda online: Odoo → conector → demo.comercio-ejemplo.example (precio, stock, oferta, despublicar, permisos; ADR 0033)
	.venv/bin/python tests/e2e/tienda_sync.py

e2e-codigos-fabrica: ## «Códigos de fábrica»: escanear el código del envase en lugar del propio 20… (módulo comercio_codigos_fabrica) en el lab
	.venv/bin/python tests/e2e/codigos_fabrica.py

e2e-factura-proveedor: ## Leer la factura de un proveedor (PDF) y agregar sus productos al catálogo (módulo comercio_factura_proveedor) en el lab
	.venv/bin/python tests/e2e/factura_proveedor.py

e2e-cierre-z: ## Cierre Z de las registradoras: cargar, confirmar (tique en el Libro IVA con el rango del día, cobros), controles y puestos sin efecto contable (comercio_cierre_z) en el lab
	.venv/bin/python tests/e2e/cierre_z.py

e2e-factura: ## Factura electrónica contra ARCA homologación en el lab, también desde las cajas, dos a la vez y con ARCA caído (Enterprise; antes: make lab-arca)
	.venv/bin/python tests/e2e/factura_electronica.py
	.venv/bin/python tests/e2e/pos_factura_arca.py

lint: ## Revisar estilo del código
	$(PY) -m ruff check src tests integrations addons/comercio_catalogo/catalogo addons/comercio_precios/calculo.py \
		addons/comercio_catalogo_ia/ia addons/comercio_pos_categorias/ia addons/comercio_factura_proveedor/factura addons/comercio_cierre_z/cierre \
		infra/docker/monitoreo infra/scripts/verificar-monitoreo.py infra/scripts/probar-listas-reales.py \
		infra/scripts/mapeos_proveedores.py infra/servidor/formato_avisos.py \
		infra/servidor/acceso_remoto_cloudflare.py infra/servidor/tailscale_ferreteria.py

ping: ## Probar la conexión con ENV
	$(IAC) ping -e $(ENV)

plan: ## Mostrar qué cambiaría en ENV (dry run)
	$(IAC) plan -e $(ENV) $(VALORES_ARG)

apply: ## Aplicar la configuración en ENV y verificarla
	$(IAC) apply -e $(ENV) $(VALORES_ARG)

verify: ## Verificar que ENV coincide con la configuración
	$(IAC) verify -e $(ENV) $(VALORES_ARG)

lab-init: ## Crear el laboratorio desde cero (base "lab" + API key en .env)
	infra/scripts/lab-init.sh

LISTAS_REALES ?= 0
COPIA ?= latest
lab-completo: ## Borrar el lab y rearmarlo entero para probar: configuración, productos de ejemplo, ARCA y la lista de ejemplo (LISTAS_REALES=1: también las reales)
	$(MAKE) lab-destroy
	$(MAKE) lab-init
	$(IAC) apply -e lab --yes
	$(PY) integrations/catalogo/importar.py -e lab data/plantillas/productos.csv --aplicar
	$(MAKE) lab-arca
	$(MAKE) lab-lista-ejemplo
	@if [ "$(LISTAS_REALES)" = "1" ]; then $(MAKE) lab-listas-reales; fi
	@echo "Lab listo: http://localhost:8069 (admin/admin). Guía: docs/runbooks/prueba-visual.md"

lab-lista-ejemplo: ## Cargar en el lab la lista de ejemplo «[EJ] Ferretera Ejemplo» (ficticia, para mostrar)
	$(PY) infra/scripts/lab-lista-ejemplo.py

lab-copia-prod: ## Restaurar en el lab la última copia de producción de R2 (base «copia_prod», neutralizada; necesita ~/copia-prod.env)
	COPIA=$(COPIA) infra/scripts/lab-copia-prod.sh

lab-copia-prod-borrar: ## Borrar del lab la base «copia_prod» (datos reales)
	STACK=lab bash -c 'source infra/scripts/lib.sh && compose exec -T odoo odoo db -c /etc/odoo/odoo.conf drop copia_prod'

lab-listas-reales: ## Cargar en el lab las listas reales de proveedores (data/privado/, si están)
	$(PY) infra/scripts/lab-listas-reales.py

listas-reales: ## Pasar todas las listas reales por el motor y comparar con la foto (al tocar catalogo/; sin lab)
	$(PY) infra/scripts/probar-listas-reales.py

listas-reales-foto: ## Guardar como foto lo que sale hoy de las listas reales (después de revisar los cambios)
	$(PY) infra/scripts/probar-listas-reales.py --guardar

lab-arca: ## Dejar el lab listo para pedir CAE a ARCA homologación (Enterprise; certificado de prueba de Odoo)
	STACK=lab bash -c 'source infra/scripts/lib.sh && compose exec -T odoo odoo shell -c /etc/odoo/odoo.conf -d lab --no-http' < infra/scripts/lab-arca-homologacion.py

lab-arca-cortar: ## Demo: simular que ARCA no responde (corta la salida del lab a homologación; volver con lab-arca-volver)
	STACK=lab bash -c 'source infra/scripts/lib.sh && compose exec -T -u root odoo sh -c "grep -q arca-cortado.invalid /etc/hosts || printf \"127.0.0.1 wswhomo.afip.gov.ar wsaahomo.afip.gov.ar arca-cortado.invalid\\n\" >> /etc/hosts"'
	@echo "==> ARCA cortado en el lab. Al terminar: make lab-arca-volver"

lab-arca-volver: ## Demo: ARCA vuelve a responder en el lab
	STACK=lab bash -c 'source infra/scripts/lib.sh && compose exec -T -u root odoo sh -c "grep -v arca-cortado.invalid /etc/hosts > /tmp/hosts; cat /tmp/hosts > /etc/hosts"'
	@echo "==> ARCA responde de nuevo en el lab"

lab-up: ## Levantar el laboratorio
	STACK=lab bash -c 'source infra/scripts/lib.sh && compose up -d --wait'

lab-red: ## Abrir el laboratorio a la red local (probar desde el celular; solo en una red de confianza)
	@if STACK=lab bash -c 'source infra/scripts/lib.sh && compose exec -T db psql -U odoo -d postgres -Atc "select 1 from pg_database where datname = '"'"'copia_prod'"'"'"' | grep -q 1; then \
		echo "Hay una copia de producción en el lab (datos reales): borrala antes con «make lab-copia-prod-borrar»." >&2; exit 1; fi
	LAB_BIND_IP=0.0.0.0 STACK=lab bash -c 'source infra/scripts/lib.sh && compose up -d --wait odoo'
	@echo "Laboratorio abierto en la red: http://$$(ip route get 1.1.1.1 | awk '{for (i = 1; i < NF; i++) if ($$i == "src") print $$(i + 1)}'):8069  (cerrar: make lab-local)"

lab-local: ## Volver a dejar el laboratorio solo en esta computadora (localhost)
	STACK=lab bash -c 'source infra/scripts/lib.sh && compose up -d --wait odoo'

lab-down: ## Detener el laboratorio (conserva los datos)
	STACK=lab bash -c 'source infra/scripts/lib.sh && compose down'

lab-destroy: ## Borrar el laboratorio y TODOS sus datos
	STACK=lab bash -c 'source infra/scripts/lib.sh && compose down -v'

lab-logs: ## Ver logs de Odoo del laboratorio
	STACK=lab bash -c 'source infra/scripts/lib.sh && compose logs -f odoo'

lab-shell: ## Abrir un shell de Odoo (Python) sobre la base del laboratorio
	STACK=lab bash -c 'source infra/scripts/lib.sh && compose exec odoo odoo shell -c /etc/odoo/odoo.conf -d lab --no-http'

lab-monitoreo: ## Levantar el monitoreo en el lab (Grafana http://localhost:3000, admin/ejemplo-lab; ADR 0028)
	MONITOREO=1 STACK=lab bash -c 'source infra/scripts/lib.sh && compose up -d --wait db && monitoreo_usuarios && \
		compose up -d --wait && compose up -d --wait --force-recreate grafana relay-discord'
	@echo "Grafana: http://localhost:3000 (admin / ejemplo-lab). Verificar: make verify-monitoreo"

web-proximamente: ## Publicar la página «Próximamente» de comercio-ejemplo.example (Cloudflare; la primera vez: npx wrangler@4 login)
	cd web/proximamente && npx --yes wrangler@4 deploy

NODE22 := PATH=$(HOME)/.local/node22/bin:$$PATH

web-tienda-demo: ## Publicar la tienda de prueba en demo.comercio-ejemplo.example: revisa tipos y pruebas, migra y publica (ADR 0032; Node 22 en ~/.local/node22)
	cd web/tienda && $(NODE22) npm ci --no-fund --no-audit && $(NODE22) npm run tipos && $(NODE22) npm test && $(NODE22) npm run db:remota && $(NODE22) npm run deploy

tienda-admin: ## Primer administrador de la tienda: make tienda-admin EMAIL=… NOMBRE="…" (después suma al resto desde /admin)
	bash infra/scripts/tienda-admin.sh "$(EMAIL)" "$(NOMBRE)"

tienda-respaldo: ## Respaldo de la base de la tienda (pedidos, clientes) en ~/respaldos-tienda, fuera del repositorio
	bash infra/scripts/tienda-respaldo.sh

web-tienda-dev: ## Tienda en local con D1 y Durable Objects simulados (http://localhost:4321)
	cd web/tienda && $(NODE22) npm run db:local && $(NODE22) npm run dev

lab-monitoreo-down: ## Apagar el monitoreo del lab (Odoo sigue andando; los datos de Grafana y Prometheus quedan)
	MONITOREO=1 STACK=lab bash -c 'source infra/scripts/lib.sh && compose rm -sf prometheus node-exporter \
		postgres-exporter blackbox cadvisor grafana relay-discord receptor-prueba'
	-docker network rm odoo-lab_monitoreo >/dev/null 2>&1

verify-monitoreo: ## Verificar el monitoreo: fuentes, tableros, alertas y cada consulta (STACK=onprem en el servidor, con sudo)
	python3 infra/scripts/verificar-monitoreo.py --stack $${STACK:-lab} $(if $(AVISOS),--probar-avisos)

tableros: ## Regenerar los tableros de Grafana (infra/docker/monitoreo/grafana/generar_tableros.py)
	python3 infra/docker/monitoreo/grafana/generar_tableros.py

backup: ## Backup del laboratorio en ./backups (STACK=onprem para el servidor)
	STACK=$${STACK:-lab} infra/scripts/backup.sh

restore-test: ## Probar la restauración de un backup: make restore-test FILE=backups/x.zip
	STACK=$${STACK:-lab} infra/scripts/restore-test.sh $(FILE)
