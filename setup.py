from distutils.core import setup
from setuptools import setup

from btrfs_sxbackup import __version__

setup(
    name='btrfs-sxbackup',
    version=__version__,
    author='Marco Schindler',
    author_email='masc@disappear.de',
    license='LICENSE',
    url='https://github.com/masc3d/btrfs-sxbackup',
    packages=['btrfs_sxbackup'],
    scripts=['README.md'],
    description='Incremental btrfs snapshot backups with push/pull support via SSH',
    long_description=open('README.md').read(),

    entry_points={
        'console_scripts':
            ['btrfs-sxbackup = btrfs_sxbackup.__main__']
    }
)

