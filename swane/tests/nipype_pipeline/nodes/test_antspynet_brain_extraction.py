import os
import sys
import types

import numpy as np
import pytest

import ants  # real antspyx (installed)
from swane.nipype_pipeline.nodes.AntsPyNetBrainExtraction import (
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


def test_keeps_only_largest_component(tmp_path):
    # fake returns a prob map with a large blob and a small detached blob
    def be(image, modality=None, **k):
        arr = np.zeros(image.shape, dtype="float32")
        arr[1:5, 1:5, 1:5] = 0.9  # large
        arr[0, 0, 0] = 0.9  # detached false positive
        return image.new_image_like(arr)

    module = types.ModuleType("antspynet")
    module.brain_extraction = be
    import sys as _sys

    _sys.modules["antspynet"] = module
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
