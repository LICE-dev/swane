"""Unit and equivalence tests for
:class:`swane.nipype_pipeline.nodes.DipyMotionCorrection.DipyMotionCorrection`.

The node performs between-volumes DWI motion correction and reorients the
gradient directions to compensate for the applied rotations. It ships two
interchangeable paths behind the same interface: a **serial** path calling
dipy's ``motion_correction`` directly (kept permanently reachable as reference
and fallback) and a **parallel** path that dispatches the per-volume affine
registrations across our own process pool. The parallel path must reassemble
volumes strictly by index and produce output bit-for-bit identical to the
serial path when the BLAS thread count matches on both sides.

Three layers, mirroring the design's "DipyMotionCorrection equivalence":

* 1a - reassembly by index: mocked registration returns identifiable payloads
  *out of order*; volume *i* must land at position *i*.
* 1b - bvec reorientation + indexing trap: a known rigid rotation must produce
  the analytic reoriented gradients, b0 rows stay ``[0, 0, 0]`` and norms are
  preserved; ``reorient_bvecs`` must be called with ``affines[..., ~b0s_mask]``
  (the non-b0 volumes only), never the full affine array.
* 1c - serial-vs-parallel oracle (``@pytest.mark.heavy``): real dipy on both
  sides with BLAS pinned to one thread, asserting exact equality.
"""

import os

import numpy as np
import nibabel as nib
import pytest

import swane.nipype_pipeline.nodes.DipyMotionCorrection as motion_module
from swane.nipype_pipeline.nodes.DipyMotionCorrection import (
    DipyMotionCorrection,
    OMP_THREADS_VAR,
    OPENBLAS_THREADS_VAR,
    _register_moving_volumes,
    _serial_motion_correction,
    _parallel_motion_correction,
)

# Everything the heavy oracle writes stays under this local, disposable root
# (the same folder that holds the real dipy test subjects); never committed.
ORACLE_ROOT = "/home/mau/test_swane/dipy_test/motion_oracle"


def _write_bval_bvec(directory, bvals, bvecs):
    """Write FSL-format bval/bvec files (bvecs as 3 rows x N cols)."""
    bval_path = os.path.join(str(directory), "dwi.bval")
    bvec_path = os.path.join(str(directory), "dwi.bvec")
    np.savetxt(bval_path, np.asarray(bvals, dtype=float)[np.newaxis, :], fmt="%g")
    np.savetxt(bvec_path, np.asarray(bvecs, dtype=float).T, fmt="%.10f")
    return bval_path, bvec_path


def _rotation_z(angle):
    """A right-handed rotation about the z axis (orthonormal 3x3)."""
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


# --------------------------------------------------------------------------- #
# Layer 1a - reassembly by index
# --------------------------------------------------------------------------- #
class TestReassemblyByIndex:
    def test_out_of_order_registration_reassembled_by_index(self):
        """A registration finishing out of order must still land at its index.

        The mock ignores the image content and returns, for volume ``i``, a 3D
        block filled with ``i`` and an affine filled with ``i``. Higher indices
        are made to finish first, so a submission-order reassembly would scramble
        the result; only index-keyed placement passes.
        """
        import time

        n_vols = 6
        shape = (3, 4, 5)
        moving = np.zeros(shape + (n_vols,), dtype=np.float64)
        ref = np.zeros(shape, dtype=np.float64)
        affine = np.eye(4)

        def mock_register(index, mov, mov_aff, static, static_aff, pipeline):
            # Later indices return sooner -> completion order is reversed.
            time.sleep((n_vols - index) * 0.01)
            return (
                index,
                np.full(shape, float(index)),
                np.full((4, 4), float(index)),
            )

        xformed, affines = _register_moving_volumes(
            moving,
            ref,
            affine,
            pipeline=motion_module.DEFAULT_PIPELINE,
            num_threads=n_vols,
            register_fn=mock_register,
            use_processes=False,
        )

        for i in range(n_vols):
            assert np.all(xformed[..., i] == i), f"volume {i} misplaced"
            assert np.all(affines[..., i] == i), f"affine {i} misplaced"


# --------------------------------------------------------------------------- #
# Layer 1b - bvec reorientation + the indexing trap
# --------------------------------------------------------------------------- #
class TestBvecReorientation:
    def _run_with_controlled_affines(
        self, workspace, monkeypatch, bvals, bvecs, rotation
    ):
        """Drive the node with the registration mocked to a known affine array.

        b0 volumes get an identity affine, non-b0 volumes get ``rotation``. The
        real ``reorient_bvecs`` runs on whatever the node passes it; a spy
        records that argument so the test can assert the indexing.
        """
        bvals = np.asarray(bvals, dtype=float)
        n_vols = bvals.shape[0]
        shape = (4, 4, 3)
        data = np.random.default_rng(0).random(shape + (n_vols,))
        affine = np.eye(4)
        in_file = os.path.join(str(workspace), "dwi.nii.gz")
        nib.save(nib.Nifti1Image(data, affine), in_file)
        bval_path, bvec_path = _write_bval_bvec(workspace, bvals, bvecs)

        # b0s_mask is what the node will compute from the bvals.
        from dipy.core.gradients import gradient_table

        gtab = gradient_table(bvals, bvecs=np.asarray(bvecs, dtype=float))
        b0s_mask = gtab.b0s_mask

        affine_array = np.zeros((4, 4, n_vols))
        affine_array[..., b0s_mask] = np.eye(4)[..., np.newaxis]
        affine_array[..., ~b0s_mask] = rotation_to_affine(rotation)[..., np.newaxis]

        def fake_motion(img, gtab_in, *args, **kwargs):
            return nib.Nifti1Image(data, affine), affine_array

        monkeypatch.setattr(motion_module, "_serial_motion_correction", fake_motion)

        recorded = {}
        real_reorient = motion_module.reorient_bvecs

        def spy_reorient(gtab_in, affines, **kwargs):
            recorded["affines"] = np.array(affines)
            return real_reorient(gtab_in, affines, **kwargs)

        monkeypatch.setattr(motion_module, "reorient_bvecs", spy_reorient)

        node = DipyMotionCorrection()
        node.inputs.in_file = in_file
        node.inputs.bval = bval_path
        node.inputs.bvec = bvec_path
        node.inputs.num_threads = 1
        node.inputs.parallel = False
        result = node.run()

        out_bvec = np.loadtxt(result.outputs.out_bvec)  # 3 x N
        return out_bvec, b0s_mask, affine_array, recorded

    def test_reorients_nonb0_only_and_preserves_b0_and_norms(
        self, workspace, monkeypatch
    ):
        # b0 at index 0, four diffusion directions after it. Positional slicing
        # of the affine array (``[..., :n_nonb0]``) would grab the b0 identity
        # and drop the last rotation -> a silent misalignment this catches.
        bvals = [0, 1000, 1000, 1000, 1000]
        bvecs = np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
                [1.0, 1.0, 0.0],
            ]
        )
        bvecs[1:] /= np.linalg.norm(bvecs[1:], axis=1, keepdims=True)
        rotation = _rotation_z(np.deg2rad(30.0))

        out_bvec, b0s_mask, affine_array, recorded = self._run_with_controlled_affines(
            workspace, monkeypatch, bvals, bvecs, rotation
        )

        # The call must pass only the non-b0 affines, keyed by ~b0s_mask.
        expected_affines = affine_array[..., ~b0s_mask]
        assert recorded["affines"].shape == expected_affines.shape
        assert recorded["affines"].shape[-1] == int(np.sum(~b0s_mask))
        assert np.array_equal(recorded["affines"], expected_affines)

        out_bvec = out_bvec.T  # -> N x 3
        # b0 row stays exactly zero.
        assert np.allclose(out_bvec[0], [0.0, 0.0, 0.0])
        # Non-b0 rows are the analytic R^T @ bvec (reorient applies the inverse
        # rotation), unit-normed.
        for i in range(1, len(bvals)):
            expected = rotation.T @ bvecs[i]
            expected /= np.linalg.norm(expected)
            assert np.allclose(
                out_bvec[i], expected, atol=1e-6
            ), f"gradient {i} not reoriented as expected"
            assert np.isclose(np.linalg.norm(out_bvec[i]), 1.0, atol=1e-6)


def rotation_to_affine(rotation):
    """Embed a 3x3 rotation into a 4x4 affine with zero translation."""
    aff = np.eye(4)
    aff[:3, :3] = rotation
    return aff


# --------------------------------------------------------------------------- #
# Layer 1c - serial vs parallel oracle (heavy: real dipy registration)
# --------------------------------------------------------------------------- #
def _make_synthetic_dwi(directory, seed=0):
    """A tiny 4D DWI with a single b0 and small inter-volume shifts.

    Written under ``directory`` so the oracle's artefacts live beside the real
    dipy test subjects and never enter the repository.
    """
    rng = np.random.default_rng(seed)
    shape = (18, 18, 8)
    n_dirs = 5
    base = rng.random(shape)
    vols = [base]  # b0
    for i in range(n_dirs):
        shifted = np.roll(base, shift=(i % 2, (i + 1) % 2, 0), axis=(0, 1, 2))
        vols.append(shifted + 0.02 * rng.random(shape))
    data = np.stack(vols, axis=-1)
    affine = np.eye(4)
    in_file = os.path.join(str(directory), "dwi.nii.gz")
    nib.save(nib.Nifti1Image(data, affine), in_file)

    bvals = [0] + [1000] * n_dirs
    bvecs = np.zeros((n_dirs + 1, 3))
    dirs = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 1.0],
        ]
    )
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    bvecs[1:] = dirs
    bval_path, bvec_path = _write_bval_bvec(directory, bvals, bvecs)
    return in_file, bval_path, bvec_path, n_dirs + 1


@pytest.mark.heavy
class TestSerialParallelOracle:
    def _run_node(self, out_dir, in_file, bval, bvec, parallel, num_threads):
        node = DipyMotionCorrection()
        node.inputs.in_file = in_file
        node.inputs.bval = bval
        node.inputs.bvec = bvec
        node.inputs.num_threads = num_threads
        node.inputs.parallel = parallel
        tag = "par" if parallel else "ser"
        node.inputs.out_file = os.path.join(out_dir, f"dwi_{tag}_{num_threads}.nii.gz")
        node.inputs.out_bvec = os.path.join(out_dir, f"dwi_{tag}_{num_threads}.bvec")
        node.inputs.out_bval = os.path.join(out_dir, f"dwi_{tag}_{num_threads}.bval")
        result = node.run()
        return result.outputs

    def test_parallel_matches_serial_bit_for_bit(self):
        os.makedirs(ORACLE_ROOT, exist_ok=True)
        in_file, bval, bvec, n_total = _make_synthetic_dwi(ORACLE_ROOT)

        # BLAS pinned to one thread on both sides so the deterministic optimiser
        # yields identical floats; loosening this would mask real bugs.
        old_omp = os.environ.get(OMP_THREADS_VAR)
        old_ob = os.environ.get(OPENBLAS_THREADS_VAR)
        os.environ[OMP_THREADS_VAR] = "1"
        os.environ[OPENBLAS_THREADS_VAR] = "1"
        try:
            serial = self._run_node(
                ORACLE_ROOT, in_file, bval, bvec, parallel=False, num_threads=1
            )
            parallel1 = self._run_node(
                ORACLE_ROOT, in_file, bval, bvec, parallel=True, num_threads=1
            )
            # Multiple workers must still reassemble to the same bytes.
            parallel2 = self._run_node(
                ORACLE_ROOT, in_file, bval, bvec, parallel=True, num_threads=2
            )
        finally:
            for var, val in (
                (OMP_THREADS_VAR, old_omp),
                (OPENBLAS_THREADS_VAR, old_ob),
            ):
                if val is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = val

        serial_data = nib.load(serial.out_file).get_fdata()
        serial_bvec = np.loadtxt(serial.out_bvec)

        for other in (parallel1, parallel2):
            other_data = nib.load(other.out_file).get_fdata()
            assert np.array_equal(
                serial_data, other_data
            ), "parallel motion-corrected volumes differ from serial"
            assert np.array_equal(
                serial_bvec, np.loadtxt(other.out_bvec)
            ), "parallel reoriented bvecs differ from serial"

        # Cheap guards: volume count preserved and no worker silently zeroed out.
        assert serial_data.shape[-1] == n_total
        for i in range(serial_data.shape[-1]):
            assert np.any(serial_data[..., i] != 0), f"volume {i} is entirely zero"

    def test_bval_passthrough_unchanged(self):
        os.makedirs(ORACLE_ROOT, exist_ok=True)
        in_file, bval, bvec, _ = _make_synthetic_dwi(ORACLE_ROOT, seed=1)
        outputs = self._run_node(
            ORACLE_ROOT, in_file, bval, bvec, parallel=True, num_threads=1
        )
        assert np.array_equal(np.loadtxt(outputs.out_bval), np.loadtxt(bval))
