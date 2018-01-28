from setuptools import setup, find_packages

setup(
    name='pywinkrelayintercom',
    version='0.0.3',
    description='Python interface to broadcast audio to Wink Relay intercoms',
    url='https://github.com/w1ll1am23/pywinkrelayintercom',
    author='William Scanlon',
    py_modules=['winkrelayintercom'],
    license='MIT',
    install_requires=[
        'pydub==0.20.0',
    ],
    zip_safe=True
)