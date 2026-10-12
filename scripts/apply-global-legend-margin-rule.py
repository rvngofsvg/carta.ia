from pathlib import Path


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 occurrence, found {count}")
    return text.replace(old, new, 1)


# ------------------------------------------------------
# app.py: all document/template families
# ------------------------------------------------------
app_path = Path("app.py")
app = app_path.read_text(encoding="utf-8")

# Legacy/premium HTML families all pass through this panel helper.
app = replace_once(
    app,
    "f'<section class=\"allergen-guide-panel\" style=\"{section_style}\">'",
    "f'<section class=\"allergen-guide-panel\" style=\"margin-left:8mm; margin-right:8mm; margin-bottom:4.5mm; {section_style}\">'",
    "generic allergen panel inset",
)

# Premium v6/v7 templates use this component.
app = replace_once(
    app,
    ".v6-guide {{ margin-top:5.5mm; padding:4.8mm;",
    ".v6-guide {{ margin:5.5mm 8mm 4.5mm; padding:4.8mm;",
    "v6 guide inset",
)

# Book/landscape: keep headers unchanged, but inset the dual footer group by 8 mm
# from each outside page edge and give the footer the same lower breathing room.
old_book_footer = '''    footer = section.footer
    footer.is_linked_to_previous = False
    footer.distance = Cm(0.25)
    footer.paragraphs[0].paragraph_format.space_after = Pt(0)
    ft = footer.add_table(rows=1, cols=3, width=usable_width)
    ft.alignment = WD_TABLE_ALIGNMENT.CENTER
    ft.autofit = False
    set_table_grid_widths(ft, [side_cm, gutter_cm, side_cm])
    set_cell_width(ft.cell(0, 0), side_cm)
    set_cell_width(ft.cell(0, 1), gutter_cm)
    set_cell_width(ft.cell(0, 2), side_cm)
    add_book_legend_side(ft.cell(0, 0), data, theme, side_width_cm=side_cm)
    add_book_legend_side(ft.cell(0, 2), data, theme, side_width_cm=side_cm)'''
new_book_footer = '''    footer = section.footer
    footer.is_linked_to_previous = False
    footer.distance = Cm(0.45)
    footer.paragraphs[0].paragraph_format.space_after = Pt(0)
    footer_usable_cm = max(12.0, usable_cm - 1.6)  # 0.8 cm extra por borde exterior
    footer_side_cm = (footer_usable_cm - gutter_cm) / 2
    ft = footer.add_table(rows=1, cols=3, width=Cm(footer_usable_cm))
    ft.alignment = WD_TABLE_ALIGNMENT.CENTER
    ft.autofit = False
    set_table_grid_widths(ft, [footer_side_cm, gutter_cm, footer_side_cm])
    set_cell_width(ft.cell(0, 0), footer_side_cm)
    set_cell_width(ft.cell(0, 1), gutter_cm)
    set_cell_width(ft.cell(0, 2), footer_side_cm)
    add_book_legend_side(ft.cell(0, 0), data, theme, side_width_cm=footer_side_cm)
    add_book_legend_side(ft.cell(0, 2), data, theme, side_width_cm=footer_side_cm)'''
app = replace_once(app, old_book_footer, new_book_footer, "book footer inset")

app = replace_once(
    app,
    "    section.bottom_margin = Cm(3.35)\n    section.header_distance = Cm(0.35)\n    section.footer_distance = Cm(0.25)",
    "    section.bottom_margin = Cm(4.2)\n    section.header_distance = Cm(0.35)\n    section.footer_distance = Cm(0.45)",
    "book page lower margin",
)

# Normal Word/PDF already use this contract after the previous fix; fail loudly if
# somebody runs this migration on an incompatible source.
required_app_contract = [
    "section.footer_distance = Cm(0.45)",
    "usable_cm = max(12.0, raw_usable_cm - 1.6)",
    "width: 164mm;",
    "grid-template-columns: repeat(7, 1fr);",
]
for needle in required_app_contract:
    if needle not in app:
        raise RuntimeError(f"missing existing main legend contract: {needle}")

app_path.write_text(app, encoding="utf-8")


# ------------------------------------------------------
# ai_design.py: Qwen Image professional menu output
# ------------------------------------------------------
ai_path = Path("ai_design.py")
ai = ai_path.read_text(encoding="utf-8")
ai = replace_once(
    ai,
    ".legend {{ margin-top:5mm; padding:2.2mm 2.5mm;",
    ".legend {{ margin:5mm 8mm 4.5mm; padding:2.2mm 2.5mm;",
    "AI design legend inset",
)
ai_path.write_text(ai, encoding="utf-8")


# ------------------------------------------------------
# serval_eider_patch: legacy python-docx safety layer
# ------------------------------------------------------
legacy_path = Path("serval_eider_patch/sitecustomize.py")
legacy = legacy_path.read_text(encoding="utf-8")
legacy = replace_once(
    legacy,
    "    section.footer_distance = Cm(0.15)\n\n    for footer in _footer_variants(section):",
    "    section.footer_distance = Cm(0.45)\n\n    for footer in _footer_variants(section):",
    "legacy portrait footer distance",
)
legacy = replace_once(
    legacy,
    "        width_cm = min(18.2, usable_cm)",
    "        width_cm = max(12.0, min(18.2, usable_cm - 1.6))  # 0.8 cm extra por lado",
    "legacy portrait side inset",
)
legacy = replace_once(
    legacy,
    "    section.footer_distance = Cm(0.12)\n    gutter_cm = 0.8\n    side_cm = max(6.0, (usable_cm - gutter_cm) / 2.0)\n    widths = (side_cm, gutter_cm, side_cm)",
    "    section.footer_distance = Cm(0.45)\n    gutter_cm = 0.8\n    content_cm = max(12.0, usable_cm - 1.6)  # 0.8 cm extra por borde exterior\n    side_cm = max(6.0, (content_cm - gutter_cm) / 2.0)\n    widths = (side_cm, gutter_cm, side_cm)",
    "legacy book footer contract",
)
legacy = replace_once(
    legacy,
    "        table = footer.add_table(rows=1, cols=3, width=Cm(usable_cm))",
    "        table = footer.add_table(rows=1, cols=3, width=Cm(content_cm))",
    "legacy book table width",
)
legacy_path.write_text(legacy, encoding="utf-8")

print("Applied global allergen legend margin contract to all template families")
