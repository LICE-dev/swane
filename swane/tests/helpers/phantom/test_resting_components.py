"""Tests for the resting-state components of the BOLD phantom.

The two networks are grey-matter signal: resting-state nuisance regression
samples the mean white-matter and CSF signals, so a network map spreading
into those tissues would make the regression remove the networks themselves.
"""

import numpy as np

from swane.tests.helpers.phantom.sequences import (
    RestingDesign,
    SequenceSpec,
    _resample,
    _resting_components,
)
from swane.tests.helpers.phantom.tissue import TissueClass as TC
from swane.tests.helpers.phantom.tissue import TissueModel

ZOOM = 2.0
BOLD_MM = 4.0
GM_CLASSES = (TC.CORTICAL_GM, TC.PRECENTRAL_GM)


def _tissue():
    """A box brain: WM core, a 6 mm cortical shell and a posterior ventricle.

    The grid spans x -40..40, y -100..20, z -20..60 mm, so the posterior
    network box (y -95..-45) holds the back face of the shell, and the
    ventricle lies 2 mm in front of it. A precentral patch sits on the top
    face of each hemisphere.
    """
    affine = np.diag([ZOOM, ZOOM, ZOOM, 1.0])
    affine[:3, 3] = (-40.0, -100.0, -20.0)
    shape = (41, 61, 41)
    ijk = np.indices(shape).reshape(3, -1).T
    x, y, z = (ijk @ affine[:3, :3].T + affine[:3, 3]).T.reshape(3, *shape)

    labels = np.full(shape, TC.AIR, dtype=np.int16)
    brain = (abs(x) <= 36) & (y >= -96) & (y <= 16) & (z >= -16) & (z <= 56)
    core = (abs(x) <= 30) & (y >= -90) & (y <= 10) & (z >= -10) & (z <= 50)
    labels[brain] = TC.CORTICAL_GM
    labels[core] = TC.WM
    labels[(abs(x) <= 10) & (y >= -88) & (y <= -70) & (z >= 0) & (z <= 20)] = (
        TC.CSF_VENTRICLE
    )
    precentral = (labels == TC.CORTICAL_GM) & (z > 50) & (y >= -20) & (y <= 0)
    precentral &= abs(x) >= 4
    labels[precentral] = TC.PRECENTRAL_GM

    return TissueModel(
        labels=labels,
        affine=affine,
        zooms=(ZOOM, ZOOM, ZOOM),
        precentral=precentral,
        cst=np.zeros(shape, bool),
        cst_dir=np.zeros(shape + (3,), np.float32),
    )


def _components(tissue, spec):
    lut = {c: 800.0 for c in TC if c != TC.AIR}
    base_native = np.vectorize(lambda c: lut.get(c, 0.0))(tissue.labels)
    psf = 0.9 * BOLD_MM
    base, affine = _resample(
        base_native.astype(np.float32),
        tissue.affine,
        spec.voxel_sizes(),
        psf,
        tissue.zooms,
        None,
    )
    design = RestingDesign(n_networks=2, n_noise=1)
    comps = _resting_components(
        design,
        tissue,
        spec,
        base,
        affine,
        psf,
        None,
        60,
        2.5,
        0.03,
        np.random.default_rng(0),
    )
    gm_native = np.isin(tissue.labels, [int(c) for c in GM_CLASSES])
    gm, _ = _resample(
        gm_native.astype(np.float32),
        tissue.affine,
        spec.voxel_sizes(),
        psf,
        tissue.zooms,
        None,
    )
    return comps, gm


def test_resting_networks_carry_no_signal_outside_grey_matter():
    spec = SequenceSpec("bold", "MR", {}, in_plane_mm=BOLD_MM, slice_mm=BOLD_MM)
    comps, gm = _components(_tissue(), spec)

    networks = comps[:2]
    assert len(networks) == 2
    no_gm = gm < 0.05
    for smap, _ in networks:
        weight = np.abs(smap)
        assert weight.sum() > 0
        # Voxels with (almost) no grey matter -- pure WM, CSF or air -- hold
        # only the partial-volume tail of the networks (a map smoothed beyond
        # the grey matter puts ~46% of its weight there).
        assert weight[no_gm].sum() / weight.sum() < 0.05
