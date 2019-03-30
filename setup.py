import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="Contrail-KeystoneDB-Sync",
    version="0.0.1",
    author="Aniruddh Amonker",
    author_email="aamonker@juniper.net",
    description="Tool to sync Keystone projects from contrail's database snapshot file",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/aniruddhamonker/Contrail-KeystoneDB-Sync.git",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 2.7",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Ubuntu14.04",
    ],
	install_requires=[
        'keystoneauth1'
    ],
    entry_points = {
        'console_scripts': ['sync-keystone=Contrail-KeystoneDB-Sync.sync_keystone:main']
    }
)