from distutils.core import setup
setup(
  name = 'trivia_core',
  packages = [
    'trivia_core',
    ],
  version = '0.1',
  license='',
  description = '',
  author = '',
  author_email = '',
  url = '',
  download_url = '',
  keywords = [],
  install_requires=[
          'Unidecode     >= 1.1.1',
          'num2words     >= 0.5.10',
          'APScheduler   >= 3.7.0',
          'tabulate      >= 0.8.7',
      ],
  classifiers=[
    'Development Status :: 4 - Beta',
    'Intended Audience :: Developers',
    'Programming Language :: Python :: >3.6',
  ],
)
