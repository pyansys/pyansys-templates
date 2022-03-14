"""A collection of useful paths pointing towards each available template."""

import os
from pathlib import Path

_PATHS_MODULE = Path(os.path.dirname(os.path.abspath(__file__)))

PYTHON_TEMPLATES_PATH = _PATHS_MODULE / "python"
"""Path to the Python templates."""

PYTHON_TEMPLATES_COMMON_PATH = PYTHON_TEMPLATES_PATH / "common"
"""Path to the Python common template."""

PYTHON_TEMPLATES_PYPKG_PATH = PYTHON_TEMPLATES_PATH / "pypkg"
"""Path to the basic Python Package template."""

PYTHON_TEMPLATES_PYPKG_ADVANCED_PATH = PYTHON_TEMPLATES_PATH / "pypkg_advanced"
"""Path to the advanced Python Package template."""
