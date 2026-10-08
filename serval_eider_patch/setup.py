from setuptools import setup

ICON_FILES = [
    "altramuces.png",
    "apio.png",
    "cacahuetes.png",
    "frutos_secos.png",
    "gambas.png",
    "gluten.png",
    "huevo.png",
    "lacteos.png",
    "moluscos.png",
    "mostaza.png",
    "pescado.png",
    "sesamo.png",
    "soja.png",
    "sulfitos.png",
]

setup(
    name="serval-eider-word-patch",
    version="1.0.4",
    py_modules=["sitecustomize"],
    data_files=[
        ("serval_eider_legend", ["leyenda_alergenos_eider.png"]),
        ("serval_eider_icons", [f"icons/{name}" for name in ICON_FILES]),
    ],
    description="Runtime Word footer and allergen icon patch for Eider",
)
