"""
Setup script for ib-util shared utilities
"""

from setuptools import setup, find_packages

setup(
    name="ib-util",
    version="0.1.0",
    description="Shared utilities for Interactive Brokers API services",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "ibapi>=9.81.1",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "python-dotenv>=1.0.0",
        "pyyaml>=6.0",
        "click>=8.0.0",
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)