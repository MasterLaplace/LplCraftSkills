"""forgeron - an unattended GitHub issue -> draft PR -> review loop driver.

The package is split so that the only module holding policy is `states`, which is
pure: it maps (record, observation) to a decision and never performs I/O. Every
side effect lives behind a port in `ports` so the whole loop can be replayed
against fakes in `tests/`.
"""

__version__ = "0.1.0"
