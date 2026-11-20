# Runbook: laboratorio

## Crear desde cero

**Antes, una vez:** el lab corre **Odoo 20 Enterprise**. El código Enterprise se clona de
GitHub (`github.com/odoo/enterprise`, rama `20.0`, con la cuenta CasaEjemplo) fuera del repo,
y su ruta va en `ODOO_ENTERPRISE_ADDONS` del `.env`. `infra/scripts/fijar-enterprise.sh` lo deja
en la misma fecha que la imagen `odoo:20.0-AAAAMMDD`. Sin esa variable el lab queda en
Community (sin CAE, Libro IVA ni lo demás de Enterprise). Detalle: «Lab Enterprise» en
`docs/infraestructura/enterprise-vs-community.md`.

```bash
make setup          # una vez: .venv con odoo-iac
make lab-init       # PostgreSQL + Odoo 20, base "lab" (es_AR, AR), API key → .env
make apply          # instala módulos y carga config/base + config/onpremise + config/ejemplos
```

O todo junto, para probar con lo que hay (borra el lab): `make lab-completo` = borrar, crear,
`apply`, productos de ejemplo, ARCA homologación (`make lab-arca`) y las listas reales de los
proveedores que estén en `data/privado/listas-proveedores/` (`make lab-listas-reales`, script
`infra/scripts/lab-listas-reales.py`; sin los archivos se saltean).

- Odoo: <http://localhost:8069> - `admin` / `admin` (solo lab).
- Correos: <http://localhost:8025> (Mailpit). Todo lo que Odoo manda por mail (recibos,
  facturas) llega a este buzón de prueba y **no sale a internet**, aunque se ponga una
  dirección real. Con `make lab-red` también se abre desde la red local.
- `make lab-init` es destructivo: recrea la base `lab`.
- La base del lab **no se registra** con el código de suscripción: Enterprise sin registrar
  avisa que quedan 30 días. Al vencer (o antes), se rearma con `make lab-completo`.
- Si se cambia `GEMINI_API_KEY` (u otra variable) en el `.env`: `make lab-up` recrea el
  contenedor con el valor nuevo. Si no, Odoo sigue con la clave vieja (síntoma: «HTTP 401 API
  key not valid» al verificar con IA).
- `make lab-red` abre el lab a la red local para probarlo desde el celular
  (`http://<IP de la PC>:8069`); `make lab-local` lo vuelve a dejar solo en esta
  computadora. Solo en una red de confianza: el lab usa `admin`/`admin`.

## Uso diario

| Acción | Comando |
|--------|---------|
| Ver qué cambiaría | `make plan` |
| Aplicar y verificar | `make apply` |
| Detectar desvíos manuales | `make verify` |
| Ver campos de un modelo | `.venv/bin/odoo-iac inspect -e lab product.template --field price` |
| Shell Python de Odoo | `make lab-shell` |
| Logs | `make lab-logs` |
| Apagar / encender | `make lab-down` / `make lab-up` |
| Borrar todo | `make lab-destroy` |

## Pruebas de punta a punta

Con el lab levantado (detalle de cada una en `make help`):

| Prueba | Qué cubre |
|--------|-----------|
| `make e2e-pos` | puesto, dos cajas con QR, balanza simulada, «Cobrado en registradora», venta con y sin factura |
| `make e2e-catalogo` | listas de proveedores |
| `make e2e-precios` | precios de venta por margen |
| `make e2e-codigos-fabrica` | códigos de fábrica |
| `make e2e-factura-proveedor` | leer facturas de proveedor |
| `make lab-arca e2e-factura` | factura electrónica contra ARCA homologación |
| `make e2e-ia` | verificación con IA y categorías del POS (llama a Gemini; requiere `GEMINI_API_KEY`) |

## Experimentar con una copia de producción

Restaurar **siempre neutralizada** y nunca commitear nada de su contenido:

```bash
STACK=lab infra/scripts/restore.sh copia.zip copia_prod --neutralize
```

Luego apuntar un entorno local (p. ej. `environments/copia.local.yaml`, ignorado por git)
a esa base para probar `plan` contra datos reales sin tocarlos.
