"""Same WeasyPrint renderer, with its official portable Windows distribution."""
import os
from pathlib import Path
import subprocess
import tempfile


def render_pdf(html, base_url):
    portable = Path(__file__).resolve().parent / '.runtime' / 'weasyprint-69' / 'dist' / 'weasyprint.exe'
    # Windows Python installations may lack Pango. The official executable
    # bundles it; Linux/deployed environments keep using the Python library.
    configured = os.environ.get('WEASYPRINT_EXECUTABLE')
    executable = Path(configured) if configured else portable
    if os.name == 'nt' and executable.is_file():
        with tempfile.TemporaryDirectory(prefix='carta_pdf_') as folder:
            src = Path(folder) / 'menu.html'
            dst = Path(folder) / 'menu.pdf'
            src.write_text(html, encoding='utf-8')
            result = subprocess.run(
                [str(executable), '--base-url', str(base_url), str(src), str(dst)],
                capture_output=True, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode or not dst.is_file():
                raise RuntimeError('WeasyPrint no pudo generar el PDF: ' + result.stderr.decode('utf-8', errors='replace')[-800:])
            return dst.read_bytes()
    from weasyprint import HTML
    return HTML(string=html, base_url=base_url).write_pdf()
