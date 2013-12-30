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
    version="0.1.0-dev",
    description='',
    author='',
    author_email='',
    url='',
    install_requires=[
        "requests>=2.0.1",
        "SQLAlchemy>=0.8.3",
        "psycopg2>=2.5.0",
        "simplejson>=3.3.1",
        "jellyfish>=0.2.1",
        "sh>=1.0.9",
        "dateutils>=0.6.6",
        "configobj>=4.7.2",
        "lxml>=3.2.3",
        "blist>=1.3.4",
        "flexidate>=1.0.0",
        "magicdate>=0.1.3",
        "jobparser>=0.1.0"
    ],
    dependency_links=["http://github.com/achernet/jellyfish/tarball/master#egg=jellyfish-0.2.1",
                      "http://github.com/achernet/jobparser/tarball/master#egg=jobparser-0.1.0"],
    packages=find_packages(exclude=['ez_setup']),
    include_package_data=True,
    test_suite='nose.collector',
    # Running easy_install for each of the below might be better
    # than running python setup.py test in a dev environment
    tests_require=[
        "nose>=1.3.0",
        "pep8>=1.4.6",
        "pylint>=0.28.0",
        "mock>=1.0.1",
        "coverage>=3.7.0",
        "epydoc>=3.0.1",
        "unittest2>=0.5.1"
    ],
    # scripts=['jobparser/bin/criteria.py'],
    zip_safe=True,
    # entry_points="""
    # [jobparser.bin.criteria]
    # main = jobparser.bin.criteria:main
    # """,
)
