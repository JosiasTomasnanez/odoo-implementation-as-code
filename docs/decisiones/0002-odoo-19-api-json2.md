# 0002. Odoo 19 en el laboratorio y API externa JSON-2

- Estado: reemplazado parcialmente por [0006](0006-odoo-20.md) (la versión pasa a 20.0; la decisión sobre JSON-2 sigue vigente)
- Fecha: 2026-09-30

## Contexto

Se necesita una versión concreta para el laboratorio y un mecanismo de
integración que funcione igual en Odoo Online y On-Premise.

Odoo 19 introdujo la API externa **JSON-2** (`POST /json/2/<modelo>/<método>`,
autenticada con API key) y deprecó XML-RPC/JSON-RPC, anunciando su eliminación
en versiones futuras.

## Decisión

- El laboratorio usa la imagen oficial `odoo:19.0` (configurable en `infra/docker/lab.env`).
- `odoo-iac` usa JSON-2 por defecto y conserva XML-RPC como alternativa
  (`protocol: xmlrpc` en el entorno) por si la instancia real lo requiere.
- Toda llamada usa argumentos por nombre, requisito de JSON-2.

Verificado en el laboratorio: ambos transportes aplican y verifican la misma configuración.

## Alternativas consideradas

- Solo XML-RPC: funciona hoy pero tiene fecha de retiro.
- Acceso directo a PostgreSQL: imposible en Online y saltea la lógica de negocio de Odoo.

## Consecuencias

- La versión del laboratorio debe alinearse con la de la instancia real (P-018).
- Cada entorno necesita una API key de un usuario técnico con los permisos mínimos
  para lo que configura (ver `docs/areas/usuarios-permisos.md`).
