# Configuration file for the Sphinx documentation builder.

import polytope

# -- Project information

project = "Polytope client"
copyright = "2021, ECMWF"
author = "ECMWF"

release = polytope.__version__

# -- General configuration

extensions = [
    "sphinx.ext.duration",
    "sphinx.ext.doctest",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
    "sphinx": ("https://www.sphinx-doc.org/en/master/", None),
}
intersphinx_disabled_domains = ["std"]

templates_path = ["_templates"]

# -- Options for HTML output

html_theme = "sphinx_rtd_theme"

# -- Options for EPUB output
epub_show_urls = "footnote"

html_extra_path = ["static"]


def setup(app):
    app.add_css_file("../my_theme.css")
