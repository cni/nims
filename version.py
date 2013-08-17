"""NIMS version/release information"""

# Format expected by setup.py and doc/source/conf.py: string of form "X.Y.Z"
_version_major = 0
_version_minor = 1
_version_micro = ''  # use '' for first of series, number for 1 and above
_version_extra = 'dev'
#_version_extra = ''  # Uncomment this for full releases

# Construct full version string from these.
_ver = [_version_major, _version_minor]
if _version_micro:
    _ver.append(_version_micro)
if _version_extra:
    _ver.append(_version_extra)

__version__ = '.'.join(map(str, _ver))

CLASSIFIERS = ["Development Status :: 3 - Alpha",
               "Environment :: Console",
               "Intended Audience :: Science/Research",
               "License :: OSI Approved :: BSD License",
               "Operating System :: OS Independent",
               "Programming Language :: Python",
               "Topic :: Scientific/Engineering"]

description = ""

long_description = """

"""

NAME = "nims"
MAINTAINER = "STANFORD CNI"
MAINTAINER_EMAIL = ""
DESCRIPTION = description
LONG_DESCRIPTION = long_description
URL = "http://github.com/cni/nims"
DOWNLOAD_URL = "http://github.com/cni/nims"
LICENSE = "https://github.com/cni/nims/tree/post#license"
AUTHOR = ""
AUTHOR_EMAIL = ""
PLATFORMS = "OS Independent"
MAJOR = _version_major
MINOR = _version_minor
MICRO = _version_micro
VERSION = __version__
PACKAGES = ['nimsdata', 'nimsapi', 'nips', 'nimsutil']
            
PACKAGE_DATA = {"nims": ["LICENSE"]}

REQUIRES = ["numpy", "scipy", "nibabel"]
