import os
import sys
import types

import numpy as np
import pytest

import ants  # real antspyx (installed)
from swane.nipype_pipeline.interfaces.ants import DEFAULT_RANDOM_SEED
from swane.nipype_pipeline.interfaces.ants.AntsPyNetBrainExtraction import (
    AntsPyNetBrainExtraction,
)


@pytest.fixture
def fake_antspynet(monkeypatch):
    """Inject a fake `antspynet` whose brain_extraction returns a real ants
    probability image derived from the input, recording the modality it saw."""
    calls = {}

    def brain_extraction(image, modality=None, **kwargs):
        calls["modality"] = modality
        arr = image.numpy()
        prob = np.zeros_like(arr, dtype="float32")
        prob[arr > arr.mean()] = 0.9  # bright voxels -> "brain"
        return image.new_image_like(prob)

    module = types.ModuleType("antspynet")
    module.brain_extraction = brain_extraction
    monkeypatch.setitem(sys.modules, "antspynet", module)
    return calls


def _write_image(path):
    arr = np.zeros((6, 6, 6), dtype="float32")
    arr[2:4, 2:4, 2:4] = 100.0
    img = ants.from_numpy(arr)
    ants.image_write(img, path)
    return path


def test_produces_brain_and_binary_mask(tmp_path, fake_antspynet):
    in_file = _write_image(str(tmp_path / "in.nii.gz"))
    node = AntsPyNetBrainExtraction()
    node.inputs.in_file = in_file
    node.inputs.modality = "t1"
    node.inputs.out_file = str(tmp_path / "brain.nii.gz")
    node.inputs.mask_file = str(tmp_path / "mask.nii.gz")
    node.run()

    assert fake_antspynet["modality"] == "t1"
    mask = ants.image_read(str(tmp_path / "mask.nii.gz")).numpy()
    assert set(np.unique(mask)).issubset({0.0, 1.0})
    assert mask.sum() > 0
    brain = ants.image_read(str(tmp_path / "brain.nii.gz")).numpy()
    # Brain image is input masked: zero wherever mask is zero.
    assert np.all(brain[mask == 0] == 0)


def test_num_threads_sets_itk_env(tmp_path, fake_antspynet):
    seen = {}

    real_be = sys.modules["antspynet"].brain_extraction

    def spy(image, modality=None, **kwargs):
        seen["itk"] = os.environ.get("ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS")
        return real_be(image, modality=modality, **kwargs)

    sys.modules["antspynet"].brain_extraction = spy
    in_file = _write_image(str(tmp_path / "in.nii.gz"))
    node = AntsPyNetBrainExtraction()
    node.inputs.in_file = in_file
    node.inputs.modality = "t2"
    node.inputs.num_threads = 3
    node.inputs.out_file = str(tmp_path / "brain.nii.gz")
    node.run()
    assert seen["itk"] == "3"


def test_tf_thread_env_vars_set(tmp_path, fake_antspynet):
    seen = {}
    real_be = sys.modules["antspynet"].brain_extraction

    def spy(image, modality=None, **kwargs):
        seen["intra"] = os.environ.get("TF_NUM_INTRAOP_THREADS")
        seen["inter"] = os.environ.get("TF_NUM_INTEROP_THREADS")
        seen["omp"] = os.environ.get("OMP_NUM_THREADS")
        return real_be(image, modality=modality, **kwargs)

    sys.modules["antspynet"].brain_extraction = spy
    in_file = _write_image(str(tmp_path / "in.nii.gz"))
    node = AntsPyNetBrainExtraction()
    node.inputs.in_file = in_file
    node.inputs.modality = "t1"
    node.inputs.num_threads = 2
    node.inputs.out_file = str(tmp_path / "brain.nii.gz")
    node.run()
    assert seen == {"intra": "2", "inter": "2", "omp": "2"}


def test_non_image_return_raises(tmp_path, monkeypatch):
    module = types.ModuleType("antspynet")
    module.brain_extraction = lambda image, modality=None, **k: {"foreground": image}
    monkeypatch.setitem(sys.modules, "antspynet", module)
    in_file = _write_image(str(tmp_path / "in.nii.gz"))
    node = AntsPyNetBrainExtraction()
    node.inputs.in_file = in_file
    node.inputs.modality = "t1threetissue"
    node.inputs.out_file = str(tmp_path / "brain.nii.gz")
    with pytest.raises(TypeError):
        node.run()


def test_keeps_only_largest_component(tmp_path, monkeypatch):
    # fake returns a prob map with a large blob and a small detached blob
    def be(image, modality=None, **k):
        arr = np.zeros(image.shape, dtype="float32")
        arr[1:5, 1:5, 1:5] = 0.9  # large
        arr[0, 0, 0] = 0.9  # detached false positive
        return image.new_image_like(arr)

    module = types.ModuleType("antspynet")
    module.brain_extraction = be
    # monkeypatch (not a bare sys.modules assignment): the fake must not stay
    # installed for the rest of the session, or a later test importing the real
    # antspynet gets this stub instead.
    monkeypatch.setitem(sys.modules, "antspynet", module)
    in_file = _write_image(str(tmp_path / "in.nii.gz"))
    node = AntsPyNetBrainExtraction()
    node.inputs.in_file = in_file
    node.inputs.modality = "t1"
    node.inputs.mask_file = str(tmp_path / "mask.nii.gz")
    node.inputs.out_file = str(tmp_path / "brain.nii.gz")
    node.run()
    mask = ants.image_read(str(tmp_path / "mask.nii.gz")).numpy()
    assert mask[0, 0, 0] == 0.0  # detached blob removed
    assert mask[1:5, 1:5, 1:5].sum() > 0


def test_threshold_default_is_half(tmp_path, fake_antspynet):
    # fake returns prob 0.6 in a block; default 0.5 keeps it as brain
    in_file = _write_image(str(tmp_path / "in.nii.gz"))
    node = AntsPyNetBrainExtraction()
    node.inputs.in_file = in_file
    node.inputs.modality = "t1"
    node.inputs.mask_file = str(tmp_path / "mask.nii.gz")
    node.inputs.out_file = str(tmp_path / "brain.nii.gz")
    node.run()
    assert ants.image_read(str(tmp_path / "mask.nii.gz")).numpy().sum() > 0


def test_threshold_is_applied(tmp_path, monkeypatch):
    # Connected prob map: a high-confidence core (0.9) inside a lower blob
    # (0.6). A higher threshold drops the 0.6 shell and keeps only the core,
    # yielding a strictly smaller mask. Both regions are made large enough that
    # the node's GetLargestComponent preserves them: on a tiny volume an empty
    # (or below-min-size) mask is turned back into a full one.
    def be(image, modality=None, **k):
        arr = np.zeros(image.shape, dtype="float32")
        arr[4:16, 4:16, 4:16] = 0.6  # outer blob (12^3)
        arr[6:14, 6:14, 6:14] = 0.9  # high-confidence core (8^3)
        return image.new_image_like(arr)

    module = types.ModuleType("antspynet")
    module.brain_extraction = be
    monkeypatch.setitem(sys.modules, "antspynet", module)
    big = np.zeros((20, 20, 20), dtype="float32")
    big[4:16, 4:16, 4:16] = 100.0
    in_file = str(tmp_path / "in.nii.gz")
    ants.image_write(ants.from_numpy(big), in_file)

    def run_at(threshold):
        node = AntsPyNetBrainExtraction()
        node.inputs.in_file = in_file
        node.inputs.modality = "t1"
        if threshold is not None:
            node.inputs.threshold = threshold
        node.inputs.mask_file = str(tmp_path / "mask.nii.gz")
        node.inputs.out_file = str(tmp_path / "brain.nii.gz")
        node.run()
        return ants.image_read(str(tmp_path / "mask.nii.gz")).numpy().sum()

    low = run_at(None)  # default 0.5 -> whole 0.6 blob is brain
    high = run_at(0.7)  # 0.6 < 0.7 -> only the 0.9 core survives
    assert high < low
    assert high == 8 * 8 * 8  # just the core


@pytest.mark.heavy
class TestRealAntsPyNetModalities:
    """Every ``DeskullModality`` must be a modality the installed antspynet knows.

    Belt and suspenders for the ``flair.v0`` risk: ``DeskullModality.VENOUS``
    uses a *previous-version* upstream network, so an antspynet release that
    drops it would only surface as ``ValueError: Unknown modality type.`` at run
    time, deep inside the venous MR workflow. The primary mitigation is the
    exact ``antspynet`` pin in ``setup.py``; this test fails loudly the moment
    the installed package stops accepting one of the keys SWANe sends.

    Real antspynet, real weights (downloaded once into ``~/.keras/ANTsXNet``),
    so it is opt-in via ``--run-heavy``.
    """

    def test_every_modality_is_accepted(self):
        antspynet = pytest.importorskip("antspynet")
        from swane.config.config_enums import DeskullModality
        from swane.tests.prerelease.antspynet_cache import preload_antspynet_models

        preload_antspynet_models(verbose=False)

        # A head-sized synthetic volume, not the 6^3 stub the mocked tests use:
        # brain_extraction really resamples to its template here, and a
        # degenerate input would fail for reasons unrelated to the modality key.
        arr = np.zeros((96, 96, 96), dtype="float32")
        arr[24:72, 24:72, 24:72] = 100.0
        image = ants.from_numpy(arr, spacing=(2.0, 2.0, 2.0))
        for modality in DeskullModality:
            try:
                antspynet.brain_extraction(image, modality=modality.value)
            except ValueError as error:
                # Only the modality key is under test here: any other
                # ValueError (a shape/spacing complaint about this synthetic
                # volume) still proves the key was recognised.
                assert "Unknown modality" not in str(
                    error
                ), "installed antspynet does not know %s=%r" % (
                    modality.name,
                    modality.value,
                )


def test_empty_mask_raises_instead_of_filling(tmp_path, monkeypatch):
    # antspynet returns a probability map that is uniformly below the threshold,
    # so the binary mask is empty. The node must raise rather than let
    # ants.iMath("GetLargestComponent") inflate the empty mask into a full-head
    # "brain" (verified antspyx 0.6.3 behaviour).
    def be(image, modality=None, **k):
        return image.new_image_like(np.full(image.shape, 0.1, dtype="float32"))

    module = types.ModuleType("antspynet")
    module.brain_extraction = be
    monkeypatch.setitem(sys.modules, "antspynet", module)

    in_file = _write_image(str(tmp_path / "in.nii.gz"))
    node = AntsPyNetBrainExtraction()
    node.inputs.in_file = in_file
    node.inputs.modality = "t1"
    node.inputs.out_file = str(tmp_path / "brain.nii.gz")
    with pytest.raises(ValueError):
        node.run()


def test_non_positive_num_threads_does_not_export_zero(tmp_path, fake_antspynet):
    # num_threads<=0 (the max_cpu=0 "auto" default) must NOT export
    # OMP_NUM_THREADS=0, which is undefined for OpenMP.
    seen = {}
    real_be = sys.modules["antspynet"].brain_extraction

    def spy(image, modality=None, **kwargs):
        seen["omp"] = os.environ.get("OMP_NUM_THREADS")
        return real_be(image, modality=modality, **kwargs)

    sys.modules["antspynet"].brain_extraction = spy

    in_file = _write_image(str(tmp_path / "in.nii.gz"))
    node = AntsPyNetBrainExtraction()
    node.inputs.in_file = in_file
    node.inputs.modality = "t1"
    node.inputs.num_threads = 0
    node.inputs.out_file = str(tmp_path / "brain.nii.gz")
    node.run()
    assert seen["omp"] != "0"


@pytest.mark.parametrize("seed", [None, 99])
def test_random_seed_is_set_then_restored(tmp_path, fake_antspynet, monkeypatch, seed):
    monkeypatch.setattr(ants.config, "_random_seed", None)
    seen = {}
    real_be = sys.modules["antspynet"].brain_extraction

    def spy(image, modality=None, **kwargs):
        # ants.registration, run by antspynet for some modalities, reads this
        # module setting for --random-seed
        seen["ants_seed"] = ants.config._random_seed
        return real_be(image, modality=modality, **kwargs)

    sys.modules["antspynet"].brain_extraction = spy

    in_file = _write_image(str(tmp_path / "in.nii.gz"))
    node = AntsPyNetBrainExtraction()
    node.inputs.in_file = in_file
    node.inputs.modality = "t1"
    if seed is not None:
        node.inputs.random_seed = seed
    node.inputs.out_file = str(tmp_path / "brain.nii.gz")
    node.run()

    assert seen["ants_seed"] == (DEFAULT_RANDOM_SEED if seed is None else seed)
    assert ants.config._random_seed is None


def test_global_random_state_is_left_untouched(tmp_path, fake_antspynet):
    """The node must not reseed the process-wide Python/NumPy generators."""
    import random

    saved_python, saved_numpy = random.getstate(), np.random.get_state()
    try:
        _check_global_random_state_is_left_untouched(tmp_path)
    finally:
        random.setstate(saved_python)
        np.random.set_state(saved_numpy)


def _check_global_random_state_is_left_untouched(tmp_path):
    import random

    random.seed(7)
    np.random.seed(7)
    expected_python = random.getstate()
    expected_numpy = np.random.get_state()

    in_file = _write_image(str(tmp_path / "in.nii.gz"))
    node = AntsPyNetBrainExtraction()
    node.inputs.in_file = in_file
    node.inputs.modality = "t1"
    node.inputs.out_file = str(tmp_path / "brain.nii.gz")
    node.run()

    assert random.getstate() == expected_python
    numpy_state = np.random.get_state()
    assert numpy_state[0] == expected_numpy[0]
    assert np.array_equal(numpy_state[1], expected_numpy[1])
    assert numpy_state[2:] == expected_numpy[2:]


def test_failed_antspynet_import_keeps_the_process_seed(tmp_path, monkeypatch):
    monkeypatch.setattr(ants.config, "_random_seed", 42)
    monkeypatch.setitem(sys.modules, "antspynet", None)  # import raises

    node = AntsPyNetBrainExtraction()
    node.inputs.in_file = _write_image(str(tmp_path / "in.nii.gz"))
    node.inputs.modality = "t1"
    node.inputs.out_file = str(tmp_path / "brain.nii.gz")
    with pytest.raises(ImportError):
        node.run()
    assert ants.config._random_seed == 42


def test_random_seed_must_be_non_zero():
    from traits.api import TraitError

    with pytest.raises(TraitError):
        AntsPyNetBrainExtraction().inputs.random_seed = 0


_REPRO_CHILD = """
import nibabel as nib
import numpy as np
from swane.nipype_pipeline.interfaces.ants.AntsPyNetBrainExtraction import (
    AntsPyNetBrainExtraction,
)
in_file, out = sys.argv[5:7]
node = AntsPyNetBrainExtraction()
node.inputs.in_file = in_file
node.inputs.modality = "t1"
node.inputs.num_threads = 1
node.inputs.out_file = "brain.nii.gz"
node.run()
np.save(out, nib.load(node._list_outputs()["out_file"]).get_fdata())
"""


@pytest.mark.heavy
class TestAntsPyNetBrainExtractionReproducibility:
    """Same input, same settings, separate single-threaded processes: the
    brain image is bit-identical.

    This checks run-to-run determinism of the node, not the seed: the "t1"
    model runs no registration. Seed forwarding is covered by
    test_random_seed_is_set_then_restored.
    """

    def test_reproducibility(self, tmp_path, run_single_thread_child):
        import antspynet

        # A real T1 head image: a synthetic phantom is not recognised as a brain
        # by the network (empty mask). S_template3 is the template antspynet
        # itself downloads to reorient the input, so no extra download.
        in_file = str(tmp_path / "t1.nii.gz")
        ants.image_write(
            ants.image_read(antspynet.get_antsxnet_data("S_template3")), in_file
        )

        outs = []
        for name in ("run_1", "run_2"):
            run_dir = tmp_path / name
            run_dir.mkdir()
            out = run_dir / "brain.npy"
            run_single_thread_child(_REPRO_CHILD, in_file, out, cwd=run_dir)
            outs.append(np.load(out))

        assert outs[0].any()
        np.testing.assert_array_equal(outs[0], outs[1])
