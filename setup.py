from setuptools import find_packages
from setuptools import setup

setup(
    name="qontract-validator",
    version="0.1.0",
    license="BSD",

    author="Red Hat App-SRE Team",
    author_email="sd-app-sre@redhat.com",

    description="Tools to validate and bundle datafiles for qontract-server",

    packages=find_packages(exclude=('tests',)),

    install_requires=[
        "anymarkup==0.7.0",
        "Click==7.0",
        "enum34==1.1.6",
        "jsonschema==2.6.0",
        "PyYAML==3.13",
        "requests==2.20.0"
    ],

    test_suite="tests",

    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.6',
    ],
    entry_points={
        'console_scripts': [
            'qontract-bundler = validator.bundler:main',
            'qontract-validator = validator.validator:main',
        ],
    },
)
