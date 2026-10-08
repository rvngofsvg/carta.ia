from setuptools import setup

setup(
    name="serval-eider-word-patch",
    version="1.0.2",
    py_modules=["sitecustomize"],
    data_files=[("serval_eider_legend", ["leyenda_alergenos_eider.webp"])],
    description="Runtime Word footer patch for Eider allergen legend",
)
