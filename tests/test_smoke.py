import importlib

import pytest


@pytest.mark.parametrize("package", ["agent", "eval", "app", "scripts"])
def test_package_imports(package: str) -> None:
    importlib.import_module(package)
