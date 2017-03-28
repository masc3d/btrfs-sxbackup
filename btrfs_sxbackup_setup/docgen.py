# Copyright (c) 2016 syntonym
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.

import argparse
import os
import os.path
import shutil

import jinja2
import glob

import btrfs_sxbackup
import btrfs_sxbackup.cli


class Generator:
    def __init__(self):
        # teplate for generated rst man pages
        self.template = """
:orphan:

{{ prog_name.replace("_", "-") }}{% if command %}-{{command}}{% endif %}
{{ "="*len(prog_name)}}={{"="*len(command)}}

Synopsis
--------

.. autoprogram:: btrfs_sxbackup.cli:parser
    :maxdepth: 1
    :prog: {{ prog_name }}
    {% if command -%}
    :start_command: {{ command }}
    {%- endif %}

{% if description -%}
Description
-----------

{{ description }}
{%- endif -%}

{%- if see_also -%}
See also
--------

{% for page in see_also -%}
:manpage:`{{ page.replace("_", "-") }}(1)`
{% endfor %}
{%- endif -%}
"""

    def _get_subparsers(self, parser):
        """Get subparsers with depth one"""
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                yield action

    def _make_rts(self, target_path, j2_template, template_arguments):
        """Render j2_template into target_path with template_arguments

        target_path        (path/str)        - where to put file
        j2_template        (jinja2.Template) - template to render
        template_arguments (dict)            - are passed to the template
        """
        template_arguments["len"] = len
        with open(target_path, mode="w") as f:
            f.write(j2_template.render(**template_arguments))

    def _make_pages(self, parser, prog_name, destination_dir):
        name = str(prog_name)
        j2_template = jinja2.Template(self.template)
        subpages = []

        for subparser in self._get_subparsers(parser):
            for choice in subparser.choices:
                subpages.append(choice)
                template_arguments = {
                        "prog_name": name,
                        "command": choice,
                        "description": "",
                        "see_also": [prog_name]
                }
                self._make_rts(os.path.join(destination_dir, choice + ".rst"), j2_template, template_arguments)

        see_also = [name.replace("_", "-") + "-" + page for page in subpages]
        template_arguments = {
                "prog_name": name,
                "command": "",
                "description": "",
                "see_also": see_also
        }

        self._make_rts(
            target_path=os.path.join(destination_dir, name.replace("_", "-")+".rst"),
            j2_template=j2_template,
            template_arguments=template_arguments)

    def run(self, out_dir: str) -> [str]:
        try:
            shutil.rmtree(out_dir)
        except FileNotFoundError:
            # out_dir does not exist, ignore
            pass
        os.makedirs(out_dir, exist_ok=True)

        self._make_pages(btrfs_sxbackup.cli.parser, "btrfs_sxbackup", out_dir)

        author = btrfs_sxbackup.__author__
        man_pages = []
        for path in glob.glob(os.path.join(out_dir, "*.rst")):
            short = os.path.basename(path).split(".")[0]
            man_pages.append((os.path.join(out_dir, short),
                              ("btrfs-sxbackup-" + short if short != "btrfs-sxbackup" else short).replace("_", "-"),
                              short, [author], 1))

        return man_pages
