from pathlib import Path
from setuptools import setup

BASE_DIR = Path(__file__).parent
legend_files = [
    str(path.relative_to(BASE_DIR))
    for path in sorted((BASE_DIR / "legend_b64").glob("part*.txt"))
]

setup(
    name="serval-eider-word-patch",
    version="1.0.1",
    py_modules=["sitecustomize"],
    data_files=[("serval_eider_legend", legend_files)],
    description="Runtime Word footer patch for Eider allergen legend",
)
