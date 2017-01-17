#!/usr/bin/python3.4

# Copyright (c) 2014 Marco Schindler
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.

import sys
import glob
import os
import sphinx
import shutil
from setuptools import setup
from setuptools.command.sdist import sdist

from btrfs_sxbackup import __version__


DOC_MAN_PATH = './docs/man'

class CustomSdist(sdist):
    """ Custom setuptools sdist command class """
    def run(self):
        input_dir = './docs/sphinx'
        build_doctree_dir = './build/doctrees'
        build_output_dir = './build/man'
        output_dir = DOC_MAN_PATH

        if os.path.exists(build_doctree_dir):
            shutil.rmtree(build_doctree_dir)
        if os.path.exists(build_output_dir):
            shutil.rmtree(build_output_dir)

        # sphinx doc generation
        sphinx.build_main(['sphinx-build',
                           '-c', input_dir,
                           '-b', 'man',
                           '-T',
                           '-d', build_doctree_dir,
                           # input dir
                           input_dir,
                           # output dir
                           build_output_dir])

        # copy to docs folder
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        shutil.copytree(build_output_dir, output_dir)

        # actual sdist
        sdist.run(self)


if sys.version_info.major < 3:
    print('btrfs-sxbackup requires python v3.x')
    sys.exit(1)

setup(
    name='btrfs-sxbackup',
    version=__version__,
    author='Marco Schindler',
    author_email='masc@disappear.de',
    license='GNU GPL',
    url='https://github.com/masc3d/btrfs-sxbackup',
    packages=['btrfs_sxbackup'],
    description='Incremental btrfs snapshot backups with push/pull support via SSH',
    long_description=open('README.rst').read(),
    data_files=[("man/man1/", glob.glob(os.path.join(DOC_MAN_PATH, '*.1')))],
    classifiers=[
        'Environment :: Console',
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: System :: Filesystems',
        'Topic :: System :: Archiving :: Backup',
        'Topic :: Utilities'],

    entry_points={
        'console_scripts': ['btrfs-sxbackup = btrfs_sxbackup.__main__:main']
    },
    cmdclass={
        'sdist': CustomSdist
    }
)
