import argparse
import os.path
import os
import sys
import jinja2
import glob

sys.path.append("..")


from btrfs_sxbackup.cli import parser

DESTINATION_DIR = "./man_pages"

# teplate for generated rst man pages
template = """
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

def get_subparsers(parser):
    """Get subparsers with depth one"""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            yield action

def make_rts(target_path, j2_template, template_arguments):
    """Render j2_template into target_path with template_arguments

    target_path        (path/str)        - where to put file
    j2_template        (jinja2.Template) - template to render
    template_arguments (dict)            - are passed to the template
    """
    template_arguments["len"] = len
    with open(target_path, mode="w") as f:
        f.write(j2_template.render(**template_arguments))

def make_pages(parser, prog_name, destination_dir):
    name = str(prog_name)
    j2_template = jinja2.Template(template)
    subpages = []

    for subparser in get_subparsers(parser):
        for choice in subparser.choices:
            subpages.append(choice)
            template_arguments = {
                    "prog_name": name,
                    "command": choice,
                    "description": "",
                    "see_also": [prog_name]
                    }
            make_rts(os.path.join(destination_dir, choice+".rst"), j2_template, template_arguments)

    see_also = [name.replace("_", "-") + "-" + page for page in subpages]
    template_arguments = {
            "prog_name": name,
            "command": "",
            "description": "",
            "see_also": see_also
            }
    make_rts(os.path.join(destination_dir, name+".rst"), j2_template, template_arguments)

import btrfs_sxbackup.cli

def main(out_dir="./man_pages"):
    make_pages(btrfs_sxbackup.cli.parser, "btrfs_sxbackup", out_dir)

def clean():
    for f in glob.glob(os.path.join(DESTINATION_DIR, "*.rst")):
        os.remove(f)

if __name__ == "__main__":
    main()
