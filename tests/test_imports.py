"""Every module under src/ must import. Most of the pipeline has no unit tests of its own, so a
syntax error there would otherwise only show up in a running worker."""

import importlib
import pkgutil

import pytest

import src

MODULES = sorted(m.name for m in pkgutil.walk_packages(src.__path__, "src.") if ".migrations." not in m.name)


@pytest.mark.parametrize("module", MODULES)
def test_module_imports(module):
    importlib.import_module(module)
