"""
Span kinds of the structured sources, as the contract `merismos:span-kinds` names them.
"""

YAML_VALUE = "yaml-value"
"""String scalar of a YAML document."""

YAML_COMMENT = "yaml-comment"
"""Comment of a YAML document."""

PYTHON_DOCSTRING = "python-docstring"
"""String literal documenting a Python module, class or function."""

PYTHON_COMMENT = "python-comment"
"""Comment of a Python module."""

COMMIT_SUBJECT = "commit-subject"
"""Subject of a commit message."""

COMMIT_BODY = "commit-body"
"""Body of a commit message, without its comment lines and its trailers."""

YAML_KINDS = (YAML_VALUE, YAML_COMMENT)
"""Every kind of a YAML source."""

PYTHON_KINDS = (PYTHON_DOCSTRING, PYTHON_COMMENT)
"""Every kind of a Python source."""

COMMIT_KINDS = (COMMIT_SUBJECT, COMMIT_BODY)
"""Every kind of a commit message."""
