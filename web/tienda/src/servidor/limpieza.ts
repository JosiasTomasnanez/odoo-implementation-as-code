// Limpieza de cada hora: lo vencido que ya no sirve (códigos, sesiones, navegadores de confianza,
// contadores de intentos viejos). Nada de esto se usa después de vencido.
export async function limpiar(env: Env): Promise<void> {
  const ahora = new Date().toISOString();
  const hace2dias = new Date(Date.now() - 2 * 86_400_000).toISOString();
  await env.DB.batch([
    env.DB.prepare("DELETE FROM codigos_ingreso WHERE vence < ?").bind(ahora),
    env.DB.prepare("DELETE FROM sesiones_cliente WHERE vence < ?").bind(ahora),
    env.DB.prepare("DELETE FROM sesiones_equipo WHERE vence < ?").bind(ahora),
    env.DB.prepare("DELETE FROM confianza_equipo WHERE vence < ?").bind(ahora),
    env.DB.prepare("DELETE FROM sesiones_panel WHERE vence < ?").bind(ahora),
    // Contadores sin bloqueo vigente y sin fallos nuevos en dos días (los anteriores a la columna «visto» también)
    env.DB.prepare("DELETE FROM intentos WHERE (hasta IS NULL OR hasta < ?) AND (visto IS NULL OR visto < ?)").bind(ahora, hace2dias),
  ]);
}
