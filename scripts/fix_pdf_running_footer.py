from __future__ import annotations

import ast
import textwrap
from pathlib import Path

APP = Path("app.py")


def replace_function(source: str, name: str, replacement: str) -> str:
    tree = ast.parse(source)
    matches = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one function {name!r}, found {len(matches)}")
    node = matches[0]
    start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
    end = node.end_lineno
    lines = source.splitlines()
    lines[start:end] = textwrap.dedent(replacement).strip("\n").splitlines()
    return "\n".join(lines).rstrip() + "\n"


PDF_BUILDER = r'''
def create_client_pdf_html(data, theme_key="neutral", with_allergens=True):
    theme = EDITABLE_WORD_THEMES.get(theme_key, EDITABLE_WORD_THEMES["neutral"])
    cat = "#" + theme.get("cat", "374151")
    text = "#" + theme.get("text", "111827")
    muted = "#" + theme.get("muted", "6B7280")
    header = "#" + theme.get("header", "1F2937")
    light = "#" + theme.get("light", "F9FAFB")
    rest = html_escape(str(data.get("restaurant_name") or "MENÚ"))

    category_html = []
    for category in data.get("categories", []):
        dishes_html = []
        for dish in category.get("dishes", []):
            icons = ""
            if with_allergens:
                for allergen in get_ordered_allergens(dish.get("allergens", [])):
                    src = file_to_data_uri(ICON_MAP.get(allergen))
                    if src:
                        icons += f'<img class="dish-icon" src="{src}" alt="{html_escape(ALLERGEN_LABELS.get(allergen, allergen))}">'
            desc = html_escape(str(dish.get("description") or ""))
            desc_html = f'<div class="desc">{desc}</div>' if desc else ""
            dishes_html.append(
                '<div class="dish">'
                f'<div class="dish-main"><span class="dish-name">{html_escape(dish_display_name(dish))}</span>'
                f'<span class="dish-icons">{icons}</span><span class="dots"></span>'
                f'<span class="price">{html_escape(format_price(dish.get("price", "")))}</span></div>{desc_html}</div>'
            )
        cat_note = html_escape(str(category.get("category_text") or ""))
        note_html = f'<div class="cat-note">{cat_note}</div>' if cat_note else ""
        category_html.append(
            f'<section class="category"><h2>{html_escape(str(category.get("name") or "Categoría"))}</h2>{note_html}{"".join(dishes_html)}</section>'
        )

    page_css = """
    @page {
        size: A4;
        margin: 15mm 15mm 16mm 15mm;
    }
    """
    footer_html = ""
    footer_css = ""

    if with_allergens:
        labels = {
            "gluten": "GLUTEN", "crustaceos": "CRUSTÁCEOS", "huevos": "HUEVOS", "pescado": "PESCADO",
            "cacahuetes": "CACAHUETES", "soja": "SOJA", "lacteos": "LÁCTEOS", "frutos de cascara": "FRUTOS DE CÁSCARA",
            "apio": "APIO", "mostaza": "MOSTAZA", "sesamo": "GRANOS DE SÉSAMO", "sulfitos": "DIÓXIDO DE AZUFRE Y SULFITOS",
            "altramuces": "ALTRAMUCES", "moluscos": "MOLUSCOS",
        }
        items = []
        for allergen in ALLERGEN_ORDER:
            src = file_to_data_uri(ICON_MAP.get(allergen))
            icon = f'<img src="{src}" alt="{html_escape(labels[allergen])}">' if src else ""
            items.append(f'<div class="legend-item">{icon}<span>{labels[allergen]}</span></div>')

        footer_html = (
            '<footer class="allergen-footer">'
            '<div class="legal">Informamos de acuerdo con el Reglamento de la UE 1169/2011, que nuestros productos contienen o pueden contener los siguientes alérgenos.</div>'
            f'<div class="legend-grid">{"".join(items)}</div>'
            '</footer>'
        )
        page_css = """
        @page {
            size: A4;
            margin: 15mm 15mm 58mm 15mm;
            @bottom-center {
                content: element(allergenFooter);
                vertical-align: bottom;
            }
        }
        """
        footer_css = """
        .allergen-footer {
            position: running(allergenFooter);
            width: 180mm;
            height: 48mm;
            border: 1.2px solid #4b4038;
            padding: 2.5mm 3mm 2mm;
            box-sizing: border-box;
            background: #fff;
            overflow: hidden;
        }
        .legal {
            text-align: center;
            font-size: 8.6pt;
            font-weight: 700;
            margin: 0 0 1.5mm;
            line-height: 1.12;
        }
        .legend-grid {
            display: flex;
            flex-wrap: wrap;
            align-content: flex-start;
            width: 100%;
        }
        .legend-item {
            width: 14.285714%;
            height: 17mm;
            text-align: center;
            font-size: 7.6pt;
            font-weight: 700;
            line-height: 1.04;
            padding: 0.3mm 0.5mm;
            box-sizing: border-box;
            hyphens: none;
            word-break: normal;
            overflow-wrap: normal;
        }
        .legend-item img {
            display: block;
            width: 9.2mm;
            height: 9.2mm;
            object-fit: contain;
            margin: 0 auto 0.6mm;
        }
        .legend-item span {
            display: block;
            white-space: normal;
            hyphens: none;
            word-break: normal;
            overflow-wrap: normal;
        }
        """

    extra = html_escape(str(data.get("texto_extra") or ""))
    extra_html = f'<div class="extra">{extra}</div>' if extra else ""

    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
    {page_css}
    *{{box-sizing:border-box}}
    body{{font-family:Arial,Helvetica,sans-serif;color:{text};margin:0;background:#fff;font-size:10.5pt;}}
    h1{{font-size:24pt;text-align:center;color:{header};margin:0 0 8mm;letter-spacing:.3px;}}
    h2{{font-size:14pt;color:{cat};border-bottom:1px solid {cat};padding-bottom:1.5mm;margin:6mm 0 2.5mm;}}
    .cat-note,.extra{{color:{muted};font-size:9pt;margin:1.5mm 0 3mm;}}
    .dish{{margin:0 0 2.2mm;break-inside:avoid;}}
    .dish-main{{display:flex;align-items:center;gap:1.6mm;font-size:11pt;}}
    .dish-name{{font-weight:700;}}
    .dish-icons{{display:inline-flex;gap:.8mm;align-items:center;}}
    .dish-icon{{width:7.5mm;height:7.5mm;object-fit:contain;}}
    .dots{{flex:1;border-bottom:1px dotted {muted};height:0;min-width:8mm;}}
    .price{{font-weight:700;white-space:nowrap;}}
    .desc{{font-size:9.2pt;color:{muted};font-style:italic;margin-top:.5mm;}}
    .extra{{padding:2.5mm;background:{light};border:1px solid #ddd;margin-top:6mm;}}
    {footer_css}
    </style></head><body>{footer_html}<h1>{rest}</h1>{''.join(category_html)}{extra_html}</body></html>"""
'''


def main() -> None:
    src = APP.read_text(encoding="utf-8")
    src = replace_function(src, "create_client_pdf_html", PDF_BUILDER)
    ast.parse(src)
    assert "position: running(allergenFooter)" in src
    assert "content: element(allergenFooter)" in src
    assert "bottom:-52mm" not in src
    APP.write_text(src, encoding="utf-8")
    print("PASS running footer PDF fix")


if __name__ == "__main__":
    main()
