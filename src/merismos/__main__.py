"""
Entry point for the `merismos` package, invoked as a module.

Usage
-----
To launch the command-line interface, execute::

    python -m merismos


See Also
--------
merismos.cli: Module implementing the application's command-line interface.
"""

from .cli import app

app()
