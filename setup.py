import re

from setuptools import setup

with open('requirements.txt') as f:
    requirements = f.read().splitlines()
    f.close()

with open('steam/__init__.py') as f:
    version = re.search(r"__version__ = ('|\")(?P<version>(?:.*?))('|\")", f.read(), re.MULTILINE).group('version')
    f.close()

if not version:
    raise RuntimeError('Version is not set')

with open('README.md') as f:
    readme = f.read()
    f.close()

setup(name='steam.py',
      author='Gobot1234',
      url='https://github.com/Gobot1234/steam.py',
      project_urls={
          "Issue tracker": 'https://github.com/Gobot1234/steam.py/issues',
      },
      version=version,
      packages=['steam'],
      license='MIT',
      description='A Python wrapper for the Steam API',
      long_description=readme,
      long_description_content_type='text/x-md',
      include_package_data=True,
      install_requires=requirements,
      python_requires='>=3.6',
      classifiers=[
          'Development Status :: 3 - Alpha',
          'License :: OSI Approved :: MIT License',
          'Intended Audience :: Developers',
          'Natural Language :: English',
          'Operating System :: OS Independent',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
          'Topic :: Software Development :: Libraries',
          'Topic :: Software Development :: Libraries :: Python Modules',
      ]
      )
