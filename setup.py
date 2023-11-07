#!/usr/bin/env python

from setuptools import setup

readme = open("README.rst").read()
history = open("HISTORY.rst").read()

setup(name="dsdrv",
      version="0.5.1",
      description="A Sony DualShock 4 userspace driver for Linux",
      url="https://github.com/chrippa/ds4drv",
      author="Christopher Rosell",
      author_email="chrippa@tanuki.se",
      license="MIT",
      long_description=readme + "\n\n" + history,
      entry_points={
        "console_scripts": ["dsdrv=dsdrv.__main__:main"]
      },
      packages=["dsdrv",
                "dsdrv.actions",
                "dsdrv.backends",
                "dsdrv.packages",
                "dsdrv.servers"],
      install_requires=["evdev>=0.3.0", "pyudev>=0.16"],
      classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.9",
        "Topic :: Games/Entertainment"
      ]
)
