import os

from setuptools import find_packages, setup

PKG_NAME = "importer"
LIB_NAME = "importer-and-mapper"
VER_FILE = "version.py"


def read_version(package: str, version_file: str) -> str:
    """
    Reads a version string from the given file, returning the corresponding string.
    This is manually read instead of imported because of the setup procedure.
    """
    version_str = "unknown"
    version_path = os.path.join(package, version_file)
    try:
        version_line = open(version_path).read()
        version_str = version_line.split("=")[-1].rstrip().replace('"', "")
        return version_str
    except OSError:
        raise RuntimeError(f"Unable to find {version_path} or file is not well formed.")

# read the requirements list
requirements = []
with open("requirements/requirements.txt") as file:
    for line in file:
        requirements.append(line)

# read the instructions to be used as long description
with open("README.md", encoding="utf-8") as fh:
    long_description = fh.read()


setup(
    name="importer-and-mapper",
    version=read_version(PKG_NAME, VER_FILE),
    packages=find_packages(exclude=["tests", "migrations"]),
    license="MIT",
    description="",
    long_description=long_description,
    long_description_content_type="text/markdown",
    install_requires=requirements,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6"
)
