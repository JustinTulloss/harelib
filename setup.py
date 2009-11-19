#!/usr/bin/env python
"""
Python Distutils setup for for amqp.  Build and install with

    python setup.py install

2007-11-10 Barry Pederson <bp@barryp.org>

"""

import sys
from distutils.core import setup, Extension

# Build the epoll extension for Linux systems with Python < 2.6
extensions = []
major, minor = sys.version_info[:2]
python_26 = (major > 2 or (major == 2 and minor >= 6))
if "linux" in sys.platform.lower() and not python_26:
    extensions.append(Extension(
        "amqplib.client_0_8.epoll", ["amqplib/client_0_8/epoll.c"]))

setup(name = "amqplib",
      description = "AMQP Client Library",
      version = "0.6.1",
      ext_modules = extensions,
      license = "LGPL",
      author = "Barry Pederson",
      author_email = "bp@barryp.org",
      url = "http://code.google.com/p/py-amqplib/",
      packages = ['amqplib', 'amqplib.client_0_8']
     )
