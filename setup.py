"""
Setup script for the pyscripts repo.
"""
try:
    from setuptools import setup, find_packages
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages

setup(
    name='pyscripts',
    version="0.1.2-dev",
    description='A convenient Git repository for several WIP python scripts',
    author='Alexander Chernetz',
    author_email='andy80586@gmail.com',
    url='https://github.com/achernet/pyscripts',
    install_requires=[line for line in open('requirements.txt', 'rb')],
    packages=find_packages(exclude=['ez_setup']),
    include_package_data=True,
    test_suite='nose.collector',
    # Running easy_install for each of the below might be better
    # than running python setup.py test in a dev environment
    tests_require=[
        "nose>=1.3.0",
        "pep8>=1.4.6",
        "pylint>=1.1.0",
        "mock>=1.0.1",
        "coverage>=3.7.1",
        "epydoc>=3.0.1",
        "unittest2>=0.5.1"
    ],
    zip_safe=False
)
