try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
    name="pyre-gevent",
    version="1.0.0",
    description="Python ZRE implementation (green version)",
    author="Arnaud Loonstra",
    author_email="arnaud@sphaero.org",
    maintainer="Tanguy Bonneau",
    maintainer_email="tanguy.bonneau@gmail.com",
    url="https://github.com/CleepDevice/pyre-gevent/",
    packages=["pyre_gevent"],
    include_package_data=True,
    python_requires=">=3.9",
    # Floors kept compatible with cleepapp-cleepbus on Cleep/Bullseye today:
    # gevent 22.10.2 + pyzmq 22.3.0 prebuild wheels (cp39 armv7l).
    install_requires=[
        "gevent>=22.10.2",
        "pyzmq>=22.3.0",
        "netaddr>=1.0.0",
        "netifaces-plus>=0.12.0",
    ],
)
