import re
import subprocess

from setuptools import setup

with open('requirements.txt') as f:
    requirements = f.read().splitlines()
    f.close()

with open('steam/__init__.py') as f:
    version = re.search(r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]', f.read(), re.MULTILINE).group(1)
    f.close()

if version is None:
    raise RuntimeError('Version is not set')

if version.endswith('+'):
    # try to find out the commit hash if checked out from git, and append
    # it to __version__ (since we use this value from setup.py, it gets
    # automatically propagated to an installed copy as well)
    version = version[:-1]  # remove '+' for PEP-440 version spec.
    try:
        ret = subprocess.run(['git', 'show', '-s', '--pretty=format:%h'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if ret.stdout:
            version = f'{version}/{ret.stdout.decode("ascii").strip()}'
    except Exception:
        pass


with open('README.md') as f:
    readme = f.read()
    f.close()

extras_require = {
    'docs': [
        'sphinx==3.1.0',
        'sphinxcontrib_trio==1.1.0',
        'sphinxcontrib-websupport',
        ''
    ]
}

setup(name='steam.py',
      author='Gobot1234',
      url='https://github.com/Gobot1234/steam.py',
      project_urls={
          "Issue tracker": 'https://github.com/Gobot1234/steam.py/issues',
      },
      version=version,
      packages=[
          'steam',
          'steam.protobufs',
          'steam.ext'
      ],
      license='MIT',
      description='A Python wrapper for the Steam API',
      long_description=readme,
      long_description_content_type='text/x-md',
      include_package_data=True,
      install_requires=requirements,
      extras_require=extras_require,
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
