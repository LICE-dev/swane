"""Fixtures for workflow-construction tests.

The shared construction fixtures (``isolated_home``, ``subject_config``,
``global_config``, ``make_input_dir``) now live one level up in
``swane/tests/nipype_pipeline/conftest.py`` so both the structural
``workflows/`` tests and the settings-matrix ``matrix/`` tests reuse a single
definition. This module is intentionally left as documentation only.
"""
