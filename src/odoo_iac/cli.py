"""Interfaz de línea de comandos.

Uso típico::

    odoo-iac ping    -e lab          # prueba conexión y muestra versión
    odoo-iac plan    -e lab          # qué cambiaría (dry run, no escribe)
    odoo-iac apply   -e lab          # aplica, previa confirmación, y verifica
    odoo-iac verify  -e lab          # falla si Odoo difiere de la configuración
    odoo-iac inspect -e lab product.template   # campos de un modelo
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from odoo_iac.client import OdooError, connect
from odoo_iac.engine import ADOPT, CREATE, INSTALL, OK, UPDATE, Engine, PlanError, Result
from odoo_iac.settings import SettingsError, load_environment
from odoo_iac.state import StateError, load_state

SYMBOLS = {CREATE: "+", ADOPT: "=", UPDATE: "~", INSTALL: "↓", OK: "✓"}
LABELS = {
    CREATE: "crear", ADOPT: "adoptar", UPDATE: "actualizar", INSTALL: "instalar", OK: "sin cambios",
}


def _short(value) -> str:
    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


def print_result(result: Result, verbose: bool = False) -> None:
    for change in result.changes:
        if change.kind == OK and not (verbose or change.note):
            continue
        line = f"{SYMBOLS[change.kind]} {LABELS[change.kind]:<11} {change.model:<24} {change.target}"
        if change.note:
            line += f"  ({change.note})"
        print(line)
        for name, (old, new) in change.diff.items():
            print(f"      {name}: {_short(old)} → {_short(new)}")
    summary = ", ".join(
        f"{result.count(kind)} {LABELS[kind]}"
        for kind in (INSTALL, CREATE, ADOPT, UPDATE, OK)
        if result.count(kind)
    )
    print(f"\nResumen: {summary or 'nada configurado'}")


def cmd_ping(args, env) -> int:
    client = connect(env)
    print(f"Conectado a {env.url} / {env.database} ({env.protocol})")
    print(f"Versión de base: {client.version()}")
    return 0


def _engine_and_state(env):
    return Engine(connect(env)), load_state(env.layers, env.values)


def cmd_plan(args, env) -> int:
    engine, state = _engine_and_state(env)
    result = engine.run(state, apply=False)
    print_result(result, args.verbose)
    return 0


def cmd_verify(args, env) -> int:
    engine, state = _engine_and_state(env)
    result = engine.run(state, apply=False)
    if result.pending():
        print_result(result, args.verbose)
        print("\n✗ Odoo no coincide con la configuración declarada.")
        return 2
    print(f"✓ Verificado: {len(result.changes)} elementos coinciden con la configuración.")
    return 0


def cmd_apply(args, env) -> int:
    engine, state = _engine_and_state(env)
    plan = engine.run(state, apply=False)
    print_result(plan, args.verbose)
    if not plan.pending():
        print("\nNo hay nada para aplicar.")
        return 0
    if not args.yes:
        answer = input(f"\n¿Aplicar estos cambios en {env.name} ({env.url})? [s/N] ")
        if answer.strip().lower() not in ("s", "si", "sí", "y", "yes"):
            print("Cancelado.")
            return 1
    engine = Engine(engine.client)
    engine.run(state, apply=True)
    print("\nCambios aplicados. Verificando...")
    return cmd_verify(args, env)


def cmd_inspect(args, env) -> int:
    client = connect(env)
    fields = client.fields_get(args.model)
    for name in sorted(fields):
        if args.field and args.field not in name:
            continue
        meta = fields[name]
        flags = "".join(
            flag for flag, key in (("R", "required"), ("r", "readonly"), ("T", "translate"))
            if meta.get(key)
        )
        relation = f" → {meta['relation']}" if meta.get("relation") else ""
        print(f"{name:<40} {meta['type']:<10} {flags:<3} {meta['string']}{relation}")
    print("\nR=requerido r=solo lectura T=traducible")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="odoo-iac", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, func, help_text):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("-e", "--env", required=True, help="entorno (environments/<env>.yaml)")
        p.add_argument("-v", "--verbose", action="store_true", help="mostrar también lo que no cambia")
        p.add_argument(
            "--valores", action="append", default=[], metavar="ARCHIVO",
            help="archivo de valores extra (p. ej. para una demo); pisa a los del entorno",
        )
        p.set_defaults(func=func)
        return p

    add("ping", cmd_ping, "probar la conexión")
    add("plan", cmd_plan, "mostrar los cambios sin aplicarlos (dry run)")
    add("verify", cmd_verify, "verificar que Odoo coincide con la configuración")
    add("apply", cmd_apply, "aplicar la configuración y verificarla").add_argument(
        "-y", "--yes", action="store_true", help="no pedir confirmación"
    )
    inspect = add("inspect", cmd_inspect, "listar los campos de un modelo")
    inspect.add_argument("model")
    inspect.add_argument("--field", help="filtrar campos que contengan este texto")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        env = load_environment(args.env)
        for extra in args.valores:
            path = Path(extra).resolve()
            if not path.is_file():
                raise SettingsError(f"No existe el archivo de valores {extra}")
            env.values.append(path)
        return args.func(args, env)
    except (SettingsError, StateError, PlanError, OdooError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
