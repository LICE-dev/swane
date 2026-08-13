"""Unit tests for :mod:`swane.nipype_pipeline.engine.NodeListEntry`.

Pure-Python container class: no external neuroimaging tool is required.

:class:`NodeListEntry` carries the display metadata of a single node (its
readable ``long_name``, the optional nested ``node_list`` for sub-workflows and
the ``node_holder`` UI item). The class declares those attributes at class
level, so these tests double as a guard that assigning fresh objects on one
instance does not leak into another.
"""

from swane.nipype_pipeline.engine.NodeListEntry import NodeListEntry


class TestNodeListEntry:
    """Behaviour of the :class:`NodeListEntry` data holder."""

    def test_default_attributes(self):
        """A fresh entry exposes the documented default values."""
        entry = NodeListEntry()
        assert entry.long_name is None
        assert entry.node_holder is None
        assert entry.node_list == {}

    def test_instance_assignment_is_isolated(self):
        """Rebinding attributes on one instance must not affect a new one.

        Assigning a *new* object (rather than mutating the shared class-level
        default in place) shadows the class attribute per instance, so a second
        entry still sees the pristine defaults.
        """
        entry = NodeListEntry()
        entry.long_name = "Some readable name"
        entry.node_list = {"child": NodeListEntry()}
        entry.node_holder = object()

        other = NodeListEntry()
        assert other.long_name is None
        assert other.node_list == {}
        assert other.node_holder is None

    def test_node_list_can_nest_entries(self):
        """``node_list`` holds child :class:`NodeListEntry` objects by name.

        This mirrors how a sub-workflow's nodes are nested under their parent
        entry when the workflow tree is built.
        """
        parent = NodeListEntry()
        child = NodeListEntry()
        child.long_name = "child node"
        parent.node_list = {"child": child}

        assert parent.node_list["child"].long_name == "child node"
