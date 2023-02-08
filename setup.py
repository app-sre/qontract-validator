from setuptools import find_packages
from setuptools import setup

setup(
    name="qontract-validator",
    version="0.1.0",
    license="BSD",

    author="Red Hat App-SRE Team",
    author_email="sd-app-sre@redhat.com",
    python_requires=">=3.9",
    description="Tools to validate and bundle datafiles for qontract-server",

    packages=find_packages(exclude=('tests',)),

    install_requires=[
        "Click~=8.1",
        "jsonschema~=3.2",
        "PyYAML~=5.3",
        "requests~=2.24",
        "jsonpath-ng~=1.5",
    ],

    test_suite="tests",

    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',

    ],
    entry_points={
        'console_scripts': [
            'qontract-bundler = validator.bundler:main',
            'qontract-validator = validator.validator:main',
        ],
    },
)
