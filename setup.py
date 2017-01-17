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


class CustomSdist(sdist):
    """ Custom setuptools sdist command class """
    def run(self):
        doctree_dir = './build/doctrees'
        output_dir = './build/man'

        if os.path.exists(doctree_dir):
            shutil.rmtree(doctree_dir)
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)

        # sphinx doc generation
        sphinx.build_main(['sphinx-build',
                           '-c', './docs/sphinx',
                           '-b', 'man',
                           '-T',
                           '-d', doctree_dir,
                           # input dir
                           './docs/sphinx',
                           # output dir
                           output_dir])

        # move to docs folder
        shutil.copytree(output_dir, './docs/man')

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
    data_files=[("man/man1/", glob.glob("docs/build/man/*.1"))],
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
