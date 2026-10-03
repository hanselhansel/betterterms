# Vendored packages

## yaml (PyYAML)

- Package: PyYAML
- Version: 6.0.3
- Source: <https://pypi.org/project/PyYAML/6.0.3/> (pure-Python source
  tree; this copy was taken from an installed wheel)
- License: MIT (see `yaml/LICENSE`)

The runtime is Python 3.11 stdlib only, so the C extension is left out:
`cyaml.py` and `_yaml*.so` are not vendored.

Do not edit files under `yaml/` except the cyaml guard in
`yaml/__init__.py`, which replaces the upstream `from .cyaml import *`
try/except with `__with_libyaml__ = False`.

To update: copy the `yaml/` package directory from a PyYAML source
distribution or installed wheel (all `*.py` except `cyaml.py`), copy its
LICENSE file to `yaml/LICENSE`, reapply the cyaml guard edit in
`yaml/__init__.py`, then update the version above and run
`python3 scripts/verify`.
