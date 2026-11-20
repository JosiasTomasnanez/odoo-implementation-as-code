# Capa `onpremise`

Ajustes que solo aplican al servidor propio (p. ej. instalar módulos de `addons/`).
Producción va en servidor propio (ADR 0007). `40-puestos.yaml` marca los 9 puestos de
`config/base` con `comercio_arma_pedidos: true` (imprimen el pedido con QR en lugar de
cobrar). El laboratorio también aplica esta capa: reproduce el servidor propio.
