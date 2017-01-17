#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime

import btrfs_sxbackup.cli
from btrfs_sxbackup_setup.docgen import Generator

# -- General configuration ------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
#
# needs_sphinx = '1.0'

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.ifconfig',
    'sphinx.ext.githubpages',
    'sphinxcontrib.autoprogram',
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# The suffix(es) of source filenames.
source_suffix = '.rst'

# The master toctree document.
master_doc = 'index'

# General information about the project.
project = 'btrfs-sxbackup'
author = btrfs_sxbackup.__author__
copyright = "{year}, {author}".format(year=datetime.datetime.now().year, author=author)

# The short X.Y version.
version = btrfs_sxbackup.__version__
# The full version, including alpha/beta/rc tags.
release = btrfs_sxbackup.__version__

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This patterns also effect to html_static_path and html_extra_path
exclude_patterns = ['build', 'Thumbs.db', '.DS_Store']

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'sphinx'

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = False

# -- Options for HTML output ----------------------------------------------

#import sphinx_rtd_theme

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = 'alabaster'

# -- Options for manual page output ---------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = Generator().run(out_dir='generated/man')
