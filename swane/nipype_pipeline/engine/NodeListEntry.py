class NodeListEntry:
    """
    Utility class used to get generic info of a Nipype Node.
    long_name: explicit name of the Node.
    node_list: if a node is a Workflow, the list of the its subnodes info stored in a list of NodeListEntry objects.
    node_holder: CustomTreeWidgetItem object to display the Node status in UI.

    """
    
    long_name = None
    node_list = {}
    node_holder = None
