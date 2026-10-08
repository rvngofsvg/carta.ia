from pathlib import Path

FILES = [Path("app.py"), Path("scripts/v12_export_polish.py")]


def patch_text(src: str) -> str:
    replacements = [
        ('"frutos de cascara": "FRUTOS DE CÁSCARA"', '"frutos de cascara": "FRUTOS DE\\nCÁSCARA"'),
        ('"sesamo": "GRANOS DE SÉSAMO"', '"sesamo": "GRANOS DE\\nSÉSAMO"'),
        ('"sulfitos": "DIÓXIDO DE AZUFRE Y SULFITOS"', '"sulfitos": "DIÓXIDO DE AZUFRE\\nY SULFITOS"'),
        ('set_cell_width(item, col_cm)\n                item.text = ""',
         'set_cell_width(item, col_cm)\n                tc_pr = item._tc.get_or_add_tcPr()\n                no_wrap = tc_pr.find(qn("w:noWrap"))\n                if no_wrap is None:\n                    no_wrap = OxmlElement("w:noWrap")\n                    tc_pr.append(no_wrap)\n                item.text = ""'),
        ('label.font.size = Pt(9.0)\n                label.bold = True',
         'label.font.size = Pt(8.6)\n                label.bold = True'),
    ]
    for old, new in replacements:
        if old in src:
            src = src.replace(old, new, 1)
        elif new not in src:
            raise RuntimeError(f"Expected token not found: {old!r}")
    return src


for path in FILES:
    src = path.read_text(encoding="utf-8")
    patched = patch_text(src)
    path.write_text(patched, encoding="utf-8")

app = Path("app.py").read_text(encoding="utf-8")
assert 'qn("w:noWrap")' in app
assert 'FRUTOS DE\\nCÁSCARA' in app
assert 'GRANOS DE\\nSÉSAMO' in app
assert 'DIÓXIDO DE AZUFRE\\nY SULFITOS' in app
assert 'label.font.size = Pt(8.6)' in app
print("PASS Word legend no-wrap repair")
