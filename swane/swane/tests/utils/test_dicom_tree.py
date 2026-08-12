from swane.utils.DicomTree import DicomTree

class FakeFrame:
    def __init__(self, pos):
        class PPS:
            def __init__(self, pos):
                self.pos = pos
            def __eq__(self, other):
                return getattr(other, 'pos', None) == self.pos
        self.PlanePositionSequence = PPS(pos)

class FakeDS:
    def __init__(self, nframes, positions):
        self.NumberOfFrames = str(nframes)
        self.PerFrameFunctionalGroupsSequence = [FakeFrame(p) for p in positions]


def test_dicom_series_add_and_refine():
    tree = DicomTree('dummy')
    tree.add_subject('S1', 'Name')
    tree.add_study('S1', 'ST1')
    series = tree.add_series('S1', 'ST1', 1)
    # add single-frame files
    series.add_dicom_loc('f1.dcm', False, 1.0, 'uid1', None)
    series.add_dicom_loc('f2.dcm', False, 2.0, 'uid2', None)
    assert series.frames == 2

    # simulate multi-frame
    tree2 = DicomTree('dummy')
    tree2.add_subject('S2', 'Name2')
    tree2.add_study('S2', 'ST2')
    series2 = tree2.add_series('S2', 'ST2', 1)
    fake_ds = FakeDS(4, [1,1,2,2])
    series2.add_dicom_loc('mf.dcm', True, None, 'sop1', fake_ds)
    # refine should set frames and volumes based on PerFrameFunctionalGroupsSequence
    series2.refine_frame_number()
    assert series2.frames == 4
    assert series2.volumes >= 1
