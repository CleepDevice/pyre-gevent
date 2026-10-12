try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
    name="pyre-gevent",
    version="0.3.6",
    description="Python ZRE implementation (green version)",
    author="Arnaud Loonstra",
    author_email="arnaud@sphaero.org",
    maintainer="Tanguy Bonneau",
    maintainer_email="tanguy.bonneau@gmail.com",
    url="http://www.github.com/tangb/pyre-gevent/",
    packages=["pyre_gevent"],
    include_package_data=True,
    python_requires=">=3.9",
    install_requires=[
        "gevent>=20.9.0",
        "pyzmq>=19.0.0",
        "netaddr>=0.8.0",
        "netifaces-plus>=0.2.0",
    ],
)
