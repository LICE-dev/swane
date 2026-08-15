"""Pre-release execution suite.

Runs the *real* SWANe workflows over the synthetic phantom exam, sweeping the
same configuration axes the ``nipype_pipeline/matrix`` snapshots cover at
construction time, and checks the produced results automatically.

Entry point::

    python -m swane.tests.prerelease --cores 8 --ram 24

See ``README.md`` in this package for the full procedure.
"""
