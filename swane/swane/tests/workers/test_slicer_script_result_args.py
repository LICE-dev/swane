import sys
from swane.workers.slicer_script_result import parse_arguments


def test_parse_arguments_defaults(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['slicer_script_result.py'])
    args = parse_arguments()
    assert hasattr(args, 'results_folder')
    assert hasattr(args, 'dti_threshold')
    assert hasattr(args, 'vein_threshold_mr')


def test_parse_arguments_custom(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['slicer_script_result.py', '--results_folder', '/tmp/results', '--dti_threshold', '0.01'])
    args = parse_arguments()
    assert args.results_folder == '/tmp/results'
    assert abs(args.dti_threshold - 0.01) < 1e-9
