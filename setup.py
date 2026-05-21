from setuptools import setup, find_packages

setup(
    name="trusttunnel-macos",
    version="1.0.0",
    description="macOS GUI client for TrustTunnel VPN protocol — windowed app with embedded console",
    author="Community",
    url="https://github.com/inhale/trusttunnel-macos",
    packages=find_packages(),
    install_requires=["toml>=0.10.0"],
    entry_points={
        "console_scripts": [
            "trusttunnel-gui=src.app:main",
        ],
    },
    python_requires=">=3.9",
    classifiers=[
        "Operating System :: MacOS :: MacOS X",
        "Programming Language :: Python :: 3",
        "Topic :: System :: Networking",
    ],
)
