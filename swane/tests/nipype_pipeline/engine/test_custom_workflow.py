"""Unit tests for :class:`swane.nipype_pipeline.engine.CustomWorkflow`.

:class:`CustomWorkflow` extends nipype's ``Workflow`` with SWANe-specific
conveniences: human-readable node labels (``format_node_name``), flattened
node/interface introspection used to drive the UI tree, and a ``sink_result``
helper that wires a ``DataSink`` for a node output. These tests build small
in-memory workflows out of ``IdentityInterface``/``Function`` nodes, so they
need nipype but no FSL/FreeSurfer/Slicer installation.
"""

from nipype import Node
from nipype.interfaces.utility import IdentityInterface, Function
from nipype.interfaces.io import DataSink

from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.engine.NodeListEntry import NodeListEntry


def _passthrough(value):
    """Trivial function body used to give ``Function`` nodes a real callable."""
    return value


def _make_function_node(name):
    """Return a ``Function`` node with a single ``out_file`` output."""
    return Node(
        Function(
            input_names=["value"],
            output_names=["out_file"],
            function=_passthrough,
        ),
        name=name,
    )


class TestFormatNodeName:
    """The static :meth:`CustomWorkflow.format_node_name` label builder."""

    def test_falls_back_to_capitalised_node_name(self):
        """With no label and an unknown interface, the node name is used.

        ``IdentityInterface`` is not registered in ``strings.node_names`` and
        the node has no ``long_name``, so the raw node name is returned with
        its first letter capitalised.
        """
        node = Node(IdentityInterface(fields=["x"]), name="myNode")
        assert CustomWorkflow.format_node_name(node) == "MyNode"

    def test_long_name_without_placeholder_is_used_verbatim(self):
        """A ``long_name`` with no ``%s`` is used as the label as-is (capitalised)."""
        node = Node(IdentityInterface(fields=["x"]), name="n")
        node.long_name = "readable label"
        assert CustomWorkflow.format_node_name(node) == "Readable label"

    def test_placeholder_without_known_interface_is_left_literal(self):
        """A ``%s`` placeholder is not substituted for an unknown interface.

        Without a default node name to inject, the placeholder is left intact.
        """
        node = Node(IdentityInterface(fields=["x"]), name="n")
        node.long_name = "before %s after"
        assert CustomWorkflow.format_node_name(node) == "Before %s after"

    def test_known_interface_default_name(self):
        """A known interface with no ``long_name`` uses its registered label.

        ``DataSink`` maps to ``"saving"`` in ``strings.node_names``.
        """
        node = Node(DataSink(), name="sink")
        assert CustomWorkflow.format_node_name(node) == "Saving"

    def test_placeholder_is_filled_with_known_interface_name(self):
        """A ``%s`` placeholder is replaced by the interface's registered label."""
        node = Node(DataSink(), name="sink")
        node.long_name = "%s results"
        assert CustomWorkflow.format_node_name(node) == "Saving results"

    def test_leading_and_trailing_whitespace_is_stripped(self):
        """The final label is stripped of surrounding whitespace before capitalising."""
        node = Node(IdentityInterface(fields=["x"]), name="n")
        node.long_name = "  padded  "
        assert CustomWorkflow.format_node_name(node) == "Padded"

    def test_dipy_recobundles_have_registered_labels(self):
        """The RecoBundles build/recognise nodes are registered.

        Without an entry in ``strings.node_names`` these would fall back to the
        raw, internal node name (e.g. "Build") in the progress UI.
        """
        from swane.nipype_pipeline.interfaces.dipy.DipyRecoBundles import (
            DipyRecoBundlesBuild,
            DipyRecoBundlesRecognize,
        )

        build = Node(DipyRecoBundlesBuild(), name="build")
        recognize = Node(DipyRecoBundlesRecognize(), name="recognize")

        assert CustomWorkflow.format_node_name(build) != "Build"
        assert CustomWorkflow.format_node_name(recognize) != "Recognize"


class TestNodeArrays:
    """Introspection helpers that expose the workflow's nodes/interfaces."""

    def test_get_node_array_skips_identity_interfaces(self):
        """``get_node_array`` omits plumbing ``IdentityInterface`` nodes.

        Only real processing nodes appear, each wrapped in a
        :class:`NodeListEntry` carrying its ``fullname``.
        """
        wf = CustomWorkflow(name="wf")
        identity = Node(IdentityInterface(fields=["x"]), name="io")
        func = _make_function_node("worker")
        wf.add_nodes([identity, func])

        array = wf.get_node_array()
        assert "io" not in array
        assert "worker" in array
        assert isinstance(array["worker"], NodeListEntry)
        assert array["worker"].fullname == func.fullname

    def test_get_node_array_recurses_into_subworkflows(self):
        """Nested :class:`CustomWorkflow` nodes are expanded into ``node_list``.

        A sub-workflow appears as an entry whose ``node_list`` holds its own
        child nodes, mirroring the workflow hierarchy for the UI tree.
        """
        top = CustomWorkflow(name="top")
        sub = CustomWorkflow(name="sub")
        child = _make_function_node("child")
        sub.add_nodes([child])
        top.add_nodes([sub])

        array = top.get_node_array()
        assert "sub" in array
        assert "child" in array["sub"].node_list

    def test_get_interface_array_excludes_identity(self):
        """``get_interface_array`` returns sorted, de-duplicated interface names.

        ``IdentityInterface`` nodes are excluded and repeated interfaces
        collapse to a single entry.
        """
        wf = CustomWorkflow(name="wf")
        wf.add_nodes(
            [
                Node(IdentityInterface(fields=["x"]), name="io"),
                _make_function_node("a"),
                _make_function_node("b"),
            ]
        )
        assert wf.get_interface_array() == ["Function"]

    def test_get_interface_array_flattens_nested_workflows(self):
        """Interfaces inside sub-workflows are flattened into the parent's list."""
        top = CustomWorkflow(name="top")
        sub = CustomWorkflow(name="sub")
        sub.add_nodes([Node(DataSink(), name="sink")])
        top.add_nodes([sub, _make_function_node("a")])
        assert top.get_interface_array() == ["DataSink", "Function"]


class TestSinkResult:
    """The :meth:`CustomWorkflow.sink_result` DataSink wiring helper."""

    def test_creates_and_configures_datasink(self, tmp_path):
        """``sink_result`` adds a named, configured ``DataSink`` node.

        The node name follows ``SaveResults_<node>_<result>`` and its
        ``base_directory``/``container``/``long_name`` are set from the call.
        """
        wf = CustomWorkflow(name="wf")
        gen = _make_function_node("gen")
        wf.add_nodes([gen])

        save_path = str(tmp_path / "out")
        wf.sink_result(
            save_path=save_path,
            result_node="gen",
            result_name="out_file",
            sub_folder="results",
        )

        sink = wf.get_node("SaveResults_gen_out_file")
        assert sink is not None
        assert sink.inputs.base_directory == save_path
        assert sink.inputs.container == "results"
        assert sink.long_name == "%s: out_file"

    def test_datasink_name_replaces_dots_in_result_name(self, tmp_path):
        """The generated node name is derived from node and result names.

        Dots in the result name are turned into underscores so the resulting
        node name is always a valid, flat identifier.
        """
        wf = CustomWorkflow(name="wf")
        gen = Node(
            Function(
                input_names=["value"],
                output_names=["nested"],
                function=_passthrough,
            ),
            name="gen",
        )
        wf.add_nodes([gen])

        wf.sink_result(
            save_path=str(tmp_path),
            result_node="gen",
            result_name="nested",
            sub_folder="sub",
        )
        assert wf.get_node("SaveResults_gen_nested") is not None


def _write_indexed_file(index):
    """Write ``r-<index>.nii.gz`` in the node's working folder, as a real
    interface does, and return its absolute path."""
    import os

    path = os.path.abspath("r-%d.nii.gz" % index)
    with open(path, "w") as handle:
        handle.write("x")
    return path


class TestSinkResultLayoutUnderUnderscoreAncestor:
    """The results layout does not depend on the subject folder's ancestors.

    ``DataSink`` with ``parameterization`` keeps every ``_``-prefixed folder
    of the source path, so an ancestor such as ``/data/_mri/`` or a CI
    runner's ``_temp`` would reach the destination. ``sink_result`` turns
    parameterization off: every file lands directly in the container folder.
    """

    @staticmethod
    def _run(subject_dir, remove_mapnode_subdir):
        """Run a SWANe-shaped graph (a sub workflow sinking into the main
        workflow's ``base_dir``) and return the saved files, relative to it."""
        from nipype import MapNode

        save_path = str(subject_dir)
        main = CustomWorkflow(name="main", base_dir=save_path)
        sub = CustomWorkflow(name="sub")
        single = Node(
            Function(
                input_names=["index"],
                output_names=["out_file"],
                function=_write_indexed_file,
            ),
            name="single",
        )
        single.inputs.index = 9
        mapped = MapNode(
            Function(
                input_names=["index"],
                output_names=["out_file"],
                function=_write_indexed_file,
            ),
            iterfield=["index"],
            name="mapped",
        )
        mapped.inputs.index = [0, 1]
        sub.add_nodes([single, mapped])
        sub.sink_result(save_path, "single", "out_file", "results")
        sub.sink_result(
            save_path,
            "mapped",
            "out_file",
            "results",
            remove_mapnode_subdir=remove_mapnode_subdir,
        )
        main.add_nodes([sub])
        main.run()

        results = subject_dir / "results"
        return sorted(p.relative_to(results).as_posix() for p in results.rglob("*.gz"))

    def test_mapnode_subdir_removed(self, tmp_path):
        """Plain Node and flattened MapNode outputs land directly in the
        container folder."""
        saved = self._run(tmp_path / "_parent" / "subj", remove_mapnode_subdir=True)
        assert saved == ["r-0.nii.gz", "r-1.nii.gz", "r-9.nii.gz"]

    def test_mapnode_without_remove_subdir_is_flat(self, tmp_path):
        """Without parameterization no ``_<name><n>`` MapNode folder is kept,
        even when ``remove_mapnode_subdir`` is not requested."""
        saved = self._run(tmp_path / "_parent" / "subj", remove_mapnode_subdir=False)
        assert saved == ["r-0.nii.gz", "r-1.nii.gz", "r-9.nii.gz"]

    def test_layout_matches_plain_ancestors(self, tmp_path):
        """A ``_``-prefixed ancestor yields the same layout as a plain one."""
        for remove in (True, False):
            plain = self._run(tmp_path / "parent" / str(remove), remove)
            underscored = self._run(tmp_path / "_parent" / str(remove), remove)
            assert underscored == plain
