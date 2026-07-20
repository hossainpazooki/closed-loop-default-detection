"""Sphinx configuration for closed-loop-default-detection.

Builds the hosted API reference. Locally:

    pip install -e ".[docs]"
    sphinx-build -b html docs docs/_build/html

On Read the Docs the build is driven by ``.readthedocs.yaml`` (installs the
package with its ``docs`` extra, then runs this config).
"""

from __future__ import annotations

import os
import sys

# Import the package without requiring an install (RTD installs it; a local
# checkout may not have). src/ layout -> add it to the path as a fallback.
sys.path.insert(0, os.path.abspath("../src"))

project = "closed-loop-default-detection"
author = "Hossain Pazooki"
copyright = "2026, Hossain Pazooki"
release = "0.2.0"
version = "0.2"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "myst_parser",
]

autosummary_generate = True
autodoc_typehints = "description"
autodoc_member_order = "bysource"
# Don't fail the whole build if an optional-at-runtime import is missing.
autodoc_mock_imports: list[str] = []
napoleon_google_docstring = True
napoleon_numpy_docstring = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
    "pandas": ("https://pandas.pydata.org/docs/", None),
    "sklearn": ("https://scikit-learn.org/stable/", None),
}

source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
master_doc = "index"
# RECON_FINDINGS.md is an internal recon/status doc and assessment.md is the
# dated accompanying article (a provenance snapshot); both live in docs/ for
# convenience but are excluded from the Sphinx build so they do not trip the
# strict `-W` toc.not_included gate.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "RECON_FINDINGS.md", "assessment.md",
                    "superpowers",   # superpowers/ = design specs, not site pages
                    "handoff",       # handoff/ = session briefs, not site pages
                    "learnings"]     # learnings/ = findings ledger, not site pages

html_theme = "furo"
html_title = "closed-loop-default-detection"
