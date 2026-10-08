from pathlib import Path

path = Path("scripts/v12_export_polish.py")
text = path.read_text(encoding="utf-8")
text = text.replace("PDF_BUILDER = r'''", 'PDF_BUILDER = r"""', 1)
text = text.replace("</body></html>'''\n'''\n\n\ndef main()", "</body></html>'''\n\"\"\"\n\n\ndef main()", 1)
path.write_text(text, encoding="utf-8")
print("PASS fixed export polish source quoting")
