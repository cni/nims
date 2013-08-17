#!/usr/bin/env python
"""Setup file for NIMS"""

import os
import sys

# BEFORE importing distutils, remove MANIFEST. distutils doesn't properly
# update it when the contents of directories change.
if os.path.exists('MANIFEST'):
    os.remove('MANIFEST')

from distutils.core import setup

# Get version and release info, which is all stored in version.py
ver_file = os.path.join('version.py')
execfile(ver_file)

opts = dict(name=NAME,
            maintainer=MAINTAINER,
            maintainer_email=MAINTAINER_EMAIL,
            description=DESCRIPTION,
            long_description=LONG_DESCRIPTION,
            url=URL,
            download_url=DOWNLOAD_URL,
            license=LICENSE,
            classifiers=CLASSIFIERS,
            author=AUTHOR,
            author_email=AUTHOR_EMAIL,
            platforms=PLATFORMS,
            version=VERSION,
            packages=PACKAGES,
            package_data=PACKAGE_DATA,
            requires=REQUIRES,
            scripts=['./scripts/'+ x for x in os.listdir('./scripts')]
            )

# For some commands, use setuptools.  Note that we do NOT list install here!
# If you want a setuptools-enhanced install, just run 'setupegg.py install'
needs_setuptools = set(('develop', ))
if len(needs_setuptools.intersection(sys.argv)) > 0:
    import setuptools

# Only add setuptools-specific flags if the user called for setuptools, but
# otherwise leave it alone
if 'setuptools' in sys.modules:
    opts['zip_safe'] = False

# Now call the actual setup function
if __name__ == '__main__':
    setup(**opts)
