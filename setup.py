try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
        name='pyre-gevent',
        version='0.3.6',
        description='Python ZRE implementation (green version)',
        author='Arnaud Loonstra',
        author_email='arnaud@sphaero.org',
        maintainer='Tanguy Bonneau',
        maintainer_email='tanguy.bonneau@gmail.com',
        url='http://www.github.com/tangb/pyre-gevent/',
        packages=['pyre_gevent'],
        include_package_data=True,
        install_requires=['pyzmq', 'ipaddress', 'netaddr', 'netifaces-plus']
)
