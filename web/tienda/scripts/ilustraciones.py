"""Genera las ilustraciones de producto de la demo (public/img/*.svg).

Son dibujos propios, para la demo con datos ficticios; en la tienda real van las fotos de la
ficha de Odoo. Uso: python3 scripts/ilustraciones.py
"""
from pathlib import Path

N, C, R, G = "#1c2733", "#02a2fe", "#d42a1c", "#6fb233"
M1, M2, M3 = "#8d969f", "#b9c0c7", "#dfe3e7"  # metal
W, K, B = "#ffffff", "#2b2b2b", "#c98a4b"  # blanco, negro, madera
Y = "#e8b923"

def svg(cuerpo: str) -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
            '<rect width="200" height="200" fill="#f3efe7"/>'
            '<ellipse cx="100" cy="172" rx="62" ry="9" fill="#1c2733" opacity=".1"/>' + cuerpo + "</svg>")

def etiqueta(x, y, w, h, color, texto="", tc=W):
    t = f'<text x="{x + w / 2}" y="{y + h / 2 + 4}" font-family="Impact,Arial Narrow,sans-serif" font-size="{min(14, h * .55)}" fill="{tc}" text-anchor="middle">{texto}</text>' if texto else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="{color}"/>' + t

D = {}
D["caja-tornillos"] = (f'<path d="M45 70 L100 50 L155 70 L155 150 L100 170 L45 150Z" fill="{C}"/>'
    f'<path d="M45 70 L100 90 L155 70 L100 50Z" fill="#5cc4ff"/><path d="M100 90 L100 170 L155 150 L155 70Z" fill="#0a7fc4"/>'
    + etiqueta(52, 105, 40, 22, W, "×100", N) +
    f'<g transform="rotate(-30 125 115)"><rect x="118" y="96" width="14" height="6" fill="{M1}"/><path d="M120 102h10v34l-5 8-5-8z" fill="{M3}"/>'
    f'<path d="M120 108l10 3M120 115l10 3M120 122l10 3M120 129l10 3" stroke="{M1}" stroke-width="2"/></g>')
D["taladro"] = (f'<path d="M40 70h95a14 14 0 0 1 14 14v12a14 14 0 0 1-14 14H40z" fill="{R}"/>'
    f'<rect x="149" y="84" width="20" height="14" fill="{K}"/><rect x="169" y="88" width="16" height="6" fill="{M2}"/>'
    f'<path d="M80 110h34l-6 50H86z" fill="{N}"/><rect x="78" y="156" width="40" height="14" rx="3" fill="{K}"/>'
    f'<rect x="96" y="112" width="10" height="16" rx="3" fill="{K}"/><path d="M50 78h40" stroke="{W}" stroke-width="4" opacity=".5"/>'
    f'<circle cx="56" cy="90" r="6" fill="{K}"/>')
D["cinta-metrica"] = (f'<rect x="45" y="60" width="96" height="96" rx="20" fill="{Y}"/><rect x="45" y="60" width="96" height="96" rx="20" fill="none" stroke="{K}" stroke-width="8"/>'
    f'<circle cx="93" cy="108" r="22" fill="{K}"/><circle cx="93" cy="108" r="8" fill="{M2}"/>'
    f'<rect x="141" y="134" width="40" height="16" fill="#f4d35e"/><path d="M147 134v6M153 134v4M159 134v6M165 134v4M171 134v6" stroke="{K}" stroke-width="1.5"/>'
    f'<rect x="178" y="130" width="5" height="24" fill="{M1}"/>')
D["candado"] = (f'<path d="M70 95V75a30 30 0 0 1 60 0v20" fill="none" stroke="{M2}" stroke-width="12"/>'
    f'<rect x="55" y="92" width="90" height="74" rx="8" fill="{Y}"/><rect x="55" y="92" width="90" height="12" fill="#f4d35e"/>'
    f'<circle cx="100" cy="128" r="8" fill="{K}"/><rect x="97" y="130" width="6" height="16" fill="{K}"/>')
D["destornilladores"] = "".join(
    f'<g transform="translate({x} 0)"><rect x="0" y="40" width="16" height="50" rx="6" fill="{col}"/><rect x="0" y="80" width="16" height="10" fill="{K}"/>'
    f'<rect x="6" y="90" width="4" height="62" fill="{M2}"/><path d="M5 152h6l-1 8h-4z" fill="{M1}"/></g>'
    for x, col in [(42, R), (62, N), (82, R), (102, N), (122, R), (142, N)])
D["cartucho"] = (f'<g transform="rotate(-20 100 110)"><rect x="80" y="45" width="40" height="110" rx="6" fill="{W}" stroke="{M2}" stroke-width="2"/>'
    + etiqueta(84, 80, 32, 46, C, "SIL", W) + f'<path d="M92 45l8-30 8 30z" fill="{M3}" stroke="{M2}" stroke-width="2"/><rect x="78" y="150" width="44" height="8" rx="2" fill="{M1}"/></g>')
D["bolsa-tarugos"] = (f'<path d="M55 60h90l8 105H47z" fill="#e9eef3" stroke="{M2}" stroke-width="2"/><rect x="55" y="50" width="90" height="14" fill="{C}"/>'
    + "".join(f'<rect x="{x}" y="{y}" width="9" height="30" rx="3" fill="{col}" transform="rotate({r} {x} {y})"/>'
              for x, y, r, col in [(70, 100, -15, "#f0c419"), (90, 95, 10, "#f0c419"), (108, 110, -5, "#f0c419"), (125, 100, 20, "#f0c419"), (80, 125, 35, "#f0c419"), (115, 130, -30, "#f0c419")])
    + etiqueta(70, 70, 60, 18, R, "N° 8", W))
D["pinza"] = (f'<path d="M100 95 L70 165" stroke="{R}" stroke-width="16" stroke-linecap="round"/><path d="M100 95 L130 165" stroke="{N}" stroke-width="16" stroke-linecap="round"/>'
    f'<path d="M92 100 L80 40 Q90 30 100 38 L106 96z" fill="{M1}"/><path d="M108 100 L120 40 Q110 30 100 38 L94 96z" fill="{M2}"/><circle cx="100" cy="98" r="8" fill="{M1}"/>')
D["llave-paso"] = (f'<rect x="35" y="95" width="130" height="30" fill="{Y}"/><rect x="35" y="90" width="18" height="40" rx="3" fill="#d6a515"/><rect x="147" y="90" width="18" height="40" rx="3" fill="#d6a515"/>'
    f'<circle cx="100" cy="110" r="28" fill="#f4d35e"/><rect x="95" y="60" width="10" height="30" fill="{M1}"/><rect x="62" y="48" width="76" height="18" rx="9" fill="{R}"/>')
D["cano"] = (f'<g transform="rotate(-25 100 110)"><rect x="20" y="96" width="160" height="28" fill="#2f8f3a"/><rect x="20" y="96" width="160" height="8" fill="#5fbf6a"/>'
    f'<ellipse cx="180" cy="110" rx="6" ry="14" fill="#1f6a29"/><ellipse cx="180" cy="110" rx="3" ry="9" fill="#f3efe7"/>'
    f'<rect x="60" y="104" width="50" height="8" fill="{W}" opacity=".8"/></g>')
D["flexible"] = (f'<path d="M40 140 C40 60, 160 60, 160 140" fill="none" stroke="{M2}" stroke-width="14"/>'
    f'<path d="M40 140 C40 60, 160 60, 160 140" fill="none" stroke="{M1}" stroke-width="14" stroke-dasharray="3 4"/>'
    f'<rect x="30" y="138" width="20" height="24" rx="2" fill="{M1}"/><rect x="150" y="138" width="20" height="24" rx="2" fill="{M1}"/>')
D["griferia"] = (f'<rect x="70" y="150" width="60" height="14" rx="4" fill="{M1}"/><rect x="88" y="70" width="24" height="82" rx="10" fill="{M2}"/>'
    f'<path d="M100 75 Q100 30 140 30 Q160 30 160 55 v18" fill="none" stroke="{M2}" stroke-width="12" stroke-linecap="round"/>'
    f'<rect x="112" y="92" width="38" height="10" rx="5" fill="{M1}"/><path d="M160 80v20" stroke="{C}" stroke-width="4" stroke-dasharray="4 4"/>')
D["teflon"] = (f'<circle cx="100" cy="110" r="46" fill="{W}" stroke="{M3}" stroke-width="3"/><circle cx="100" cy="110" r="22" fill="{R}"/><circle cx="100" cy="110" r="14" fill="#f3efe7"/>'
    f'<path d="M146 112 L176 160 L168 166 L140 122z" fill="{W}" stroke="{M3}" stroke-width="2"/>')
D["cable"] = (f'<circle cx="100" cy="108" r="58" fill="{R}"/>' + "".join(f'<circle cx="100" cy="108" r="{r}" fill="none" stroke="#a71f14" stroke-width="2"/>' for r in (50, 42, 34))
    + f'<circle cx="100" cy="108" r="22" fill="#f3efe7"/>' + etiqueta(70, 98, 60, 20, W, "2,5 mm²", N)
    + f'<path d="M150 140 Q175 150 168 172" fill="none" stroke="{R}" stroke-width="6"/>')
D["lampara"] = (f'<circle cx="100" cy="82" r="44" fill="{W}" stroke="{M3}" stroke-width="3"/><path d="M78 115h44l-4 18H82z" fill="{W}" stroke="{M3}" stroke-width="3"/>'
    f'<rect x="82" y="133" width="36" height="26" fill="{M2}"/><path d="M82 139h36M82 146h36M82 153h36" stroke="{M1}" stroke-width="3"/>'
    f'<path d="M94 168h12l-2 6h-8z" fill="{K}"/><path d="M100 20v-6M140 36l5-5M60 36l-5-5" stroke="{Y}" stroke-width="4" stroke-linecap="round"/>')
D["cinta-aisladora"] = (f'<circle cx="100" cy="110" r="48" fill="{K}"/><circle cx="100" cy="110" r="48" fill="none" stroke="#444" stroke-width="2"/>'
    f'<circle cx="100" cy="110" r="26" fill="{C}"/><circle cx="100" cy="110" r="18" fill="#f3efe7"/><path d="M148 110 L180 128 L176 138 L144 122z" fill="{K}"/>')
D["zapatilla"] = (f'<rect x="25" y="95" width="150" height="40" rx="8" fill="{W}" stroke="{M3}" stroke-width="3"/>'
    + "".join(f'<circle cx="{x}" cy="115" r="9" fill="#eef1f4" stroke="{M2}" stroke-width="2"/><circle cx="{x - 3}" cy="115" r="1.6" fill="{M1}"/><circle cx="{x + 3}" cy="115" r="1.6" fill="{M1}"/>' for x in (50, 74, 98, 122))
    + f'<rect x="140" y="105" width="22" height="20" rx="3" fill="{R}"/><path d="M25 115 Q5 115 10 150 Q15 170 40 165" fill="none" stroke="{M3}" stroke-width="6"/>')
D["termica"] = (f'<rect x="60" y="40" width="80" height="125" rx="4" fill="{W}" stroke="{M3}" stroke-width="3"/><rect x="60" y="95" width="80" height="10" fill="{M3}"/>'
    f'<rect x="72" y="62" width="22" height="26" rx="2" fill="{N}"/><rect x="106" y="62" width="22" height="26" rx="2" fill="{N}"/><rect x="72" y="62" width="56" height="8" fill="{N}"/>'
    + etiqueta(76, 120, 48, 16, C, "C20", W) + f'<rect x="70" y="145" width="60" height="6" fill="{M2}"/>')
D["reflector"] = (f'<rect x="45" y="55" width="110" height="80" rx="8" fill="{N}"/><rect x="55" y="65" width="90" height="60" rx="4" fill="#fff6cf"/>'
    + "".join(f'<circle cx="{x}" cy="{y}" r="4" fill="#ffe27a"/>' for x in (70, 85, 100, 115, 130) for y in (80, 95, 110))
    + f'<path d="M75 135 L70 160 H130 L125 135" fill="none" stroke="{N}" stroke-width="8"/>')
D["balde-cloro"] = (f'<path d="M50 70h100l-10 95H60z" fill="{C}"/><rect x="45" y="62" width="110" height="14" rx="4" fill="#0a7fc4"/>'
    f'<path d="M55 68 Q100 15 145 68" fill="none" stroke="{M2}" stroke-width="5"/>' + etiqueta(62, 95, 76, 40, W, "CLORO", C)
    + f'<rect x="72" y="140" width="56" height="12" fill="{R}"/><text x="100" y="150" font-family="Impact,sans-serif" font-size="10" fill="{W}" text-anchor="middle">10 KG</text>')
D["pastillas"] = (f'<rect x="50" y="55" width="100" height="110" rx="10" fill="{C}"/><rect x="50" y="55" width="100" height="24" rx="10" fill="#0a7fc4"/>'
    + "".join(f'<circle cx="{x}" cy="{y}" r="15" fill="{W}" stroke="{M3}" stroke-width="2"/>' for x, y in ((78, 105), (122, 105), (100, 140)))
    + etiqueta(70, 160, 60, 14, R, "×5", W))
D["limpiafondo"] = (f'<path d="M40 130 L60 100 H140 L160 130z" fill="{C}"/><rect x="38" y="130" width="124" height="14" rx="4" fill="{N}"/>'
    + "".join(f'<circle cx="{x}" cy="150" r="8" fill="{K}"/>' for x in (55, 85, 115, 145))
    + f'<rect x="92" y="40" width="16" height="62" fill="{M2}"/><path d="M100 40 Q100 20 130 22" fill="none" stroke="{N}" stroke-width="10" stroke-linecap="round"/>')
D["barrefondo"] = (f'<rect x="30" y="118" width="140" height="22" rx="6" fill="{N}"/>' + "".join(f'<rect x="{x}" y="140" width="4" height="18" fill="{C}"/>' for x in range(36, 166, 8))
    + f'<rect x="92" y="40" width="16" height="80" fill="{M2}"/><rect x="85" y="104" width="30" height="16" rx="3" fill="{C}"/>')
D["latex"] = (f'<path d="M50 65h100v95a6 6 0 0 1-6 6H56a6 6 0 0 1-6-6z" fill="{W}" stroke="{M3}" stroke-width="3"/><rect x="46" y="58" width="108" height="14" rx="4" fill="{M2}"/>'
    f'<path d="M56 64 Q100 18 144 64" fill="none" stroke="{M1}" stroke-width="5"/>' + etiqueta(58, 88, 84, 42, R, "LÁTEX", W)
    + f'<rect x="58" y="136" width="84" height="16" fill="{C}"/><text x="100" y="148" font-family="Impact,sans-serif" font-size="11" fill="{W}" text-anchor="middle">20 L · MATE</text>')
D["rodillo"] = (f'<rect x="40" y="50" width="110" height="40" rx="18" fill="#f1e9dc"/>' + "".join(f'<path d="M{x} 54v32" stroke="#d9ccb6" stroke-width="3"/>' for x in range(52, 146, 10))
    + f'<path d="M150 70 H165 V110 H105 V128" fill="none" stroke="{M1}" stroke-width="6"/><rect x="96" y="124" width="18" height="48" rx="7" fill="{R}"/>')
D["pincel"] = (f'<g transform="rotate(25 100 100)"><rect x="90" y="20" width="20" height="80" rx="8" fill="{B}"/><rect x="84" y="96" width="32" height="22" fill="{M2}"/>'
    f'<path d="M84 118h32l-2 48H86z" fill="#5b3a21"/><path d="M90 120v42M98 120v44M106 120v44M112 120v40" stroke="#7a5233" stroke-width="2"/></g>')
D["enduido"] = (f'<path d="M58 80h84l-6 80H64z" fill="{W}" stroke="{M3}" stroke-width="3"/><rect x="54" y="68" width="92" height="16" rx="4" fill="{C}"/>'
    + etiqueta(66, 100, 68, 36, N, "ENDUIDO", W))
D["manguera"] = ("".join(f'<ellipse cx="100" cy="112" rx="{r}" ry="{r * .72}" fill="none" stroke="{col}" stroke-width="9"/>' for r, col in ((62, G), (50, "#5aa02a"), (38, G), (26, "#5aa02a")))
    + f'<rect x="150" y="104" width="22" height="16" rx="3" fill="{Y}"/><path d="M162 112 Q175 150 150 168" fill="none" stroke="{G}" stroke-width="9"/>')
D["pistola-riego"] = (f'<path d="M50 70h80a10 10 0 0 1 10 10v8a10 10 0 0 1-10 10H50z" fill="{G}"/><rect x="140" y="72" width="26" height="22" rx="4" fill="{N}"/>'
    f'<circle cx="166" cy="83" r="12" fill="{N}"/><path d="M70 98 L58 160 H84 L92 98z" fill="#5aa02a"/><path d="M92 104 Q106 116 96 132" fill="none" stroke="{N}" stroke-width="7" stroke-linecap="round"/>'
    f'<rect x="54" y="155" width="34" height="14" rx="3" fill="{Y}"/>')
D["tijera-podar"] = (f'<path d="M100 105 L70 165" stroke="{R}" stroke-width="16" stroke-linecap="round"/><path d="M100 105 L130 165" stroke="{R}" stroke-width="16" stroke-linecap="round"/>'
    f'<path d="M95 108 Q60 60 92 30 Q100 70 108 100z" fill="{M2}"/><path d="M105 108 Q130 70 118 40 Q104 72 96 100z" fill="{M1}"/><circle cx="100" cy="106" r="7" fill="{N}"/>')
D["alimento-perro"] = (f'<path d="M55 55 Q100 45 145 55 L150 165 Q100 172 50 165z" fill="{R}"/><path d="M55 55 Q100 45 145 55 L146 70 Q100 62 54 70z" fill="#a71f14"/>'
    f'<circle cx="100" cy="112" r="30" fill="{Y}"/><circle cx="90" cy="106" r="4" fill="{K}"/><circle cx="110" cy="106" r="4" fill="{K}"/><ellipse cx="100" cy="120" rx="8" ry="5" fill="{K}"/>'
    f'<path d="M72 96 Q66 120 78 124M128 96 Q134 120 122 124" fill="#b07d1a"/>' + etiqueta(70, 146, 60, 14, W, "15 KG", R))
D["piedras-gato"] = (f'<path d="M60 55 Q100 48 140 55 L146 165 Q100 172 54 165z" fill="#8c5bd6"/><path d="M60 55 Q100 48 140 55 L141 68 Q100 62 59 68z" fill="#6b3fb3"/>'
    f'<path d="M80 125 l8-22 8 14 8-14 8 22z" fill="{W}"/><circle cx="100" cy="128" r="20" fill="{W}"/><circle cx="93" cy="126" r="2.5" fill="{K}"/><circle cx="107" cy="126" r="2.5" fill="{K}"/>'
    + etiqueta(72, 150, 56, 12, Y, "4 KG", N))
D["correa"] = (f'<rect x="45" y="70" width="70" height="70" rx="30" fill="{C}"/><circle cx="80" cy="105" r="16" fill="#f3efe7"/><rect x="72" y="72" width="16" height="8" rx="3" fill="{R}"/>'
    f'<path d="M115 105 Q150 105 160 150" fill="none" stroke="{N}" stroke-width="4"/><circle cx="162" cy="156" r="6" fill="none" stroke="{M1}" stroke-width="3"/>'
    f'<path d="M70 140 Q60 165 80 168 H90 Q100 165 92 140" fill="{N}"/>')

DESTINO = Path(__file__).resolve().parent.parent / "public" / "img"
DESTINO.mkdir(parents=True, exist_ok=True)
for nombre, cuerpo in D.items():
    (DESTINO / f"{nombre}.svg").write_text(svg(cuerpo), encoding="utf-8")
print(len(D), "ilustraciones en", DESTINO)
