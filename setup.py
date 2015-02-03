import sys

from setuptools import setup

from btrfs_sxbackup import __version__


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
        'console_scripts': ['btrfs-sxbackup = btrfs_sxbackup.__main__']
    }
)

