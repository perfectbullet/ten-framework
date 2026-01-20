"""
Speaker Recognition SDK
A speaker recognition SDK using FunASR CampPlus model
"""

from pathlib import Path
from setuptools import setup, find_packages

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = [
    line.strip()
    for line in requirements_file.read_text().splitlines()
    if line.strip() and not line.startswith("#")
]

setup(
    name="speaker-recognition-sdk",
    version="0.1.0",
    description="Speaker Recognition SDK using FunASR CampPlus model",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="",
    python_requires=">=3.8",
    packages=find_packages(),
    include_package_data=True,
    install_requires=requirements,
    extras_require={
        "dev": [
            "black>=23.0.0",
            "ruff>=0.1.0",
            "mypy>=1.5.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "speaker-recognition=speaker_recognition.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
