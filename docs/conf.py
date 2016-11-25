#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import os.path
import sys
import datetime
import glob

sys.path.insert(0, os.path.abspath('..'))

import btrfs_sxbackup

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
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

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
man_pages = [
]


for path in glob.glob("man_pages/*.rst"):
    short = os.path.basename(path).split(".")[0]
    man_pages.append(("man_pages/" + short, 
        ("btrfs-sxbackup-"+short if short != "btrfs_sxbackup" else short).replace("_", "-"),
        short, [author], 1))
