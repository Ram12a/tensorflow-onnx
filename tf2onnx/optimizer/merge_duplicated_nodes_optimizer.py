# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT license.

"""Merge Duplicated Nodes Optimizer.
   Remove duplicate nodes except identity nodes which should be handled by identity optimizer.
   for example, node a is input of node b and node c, and computation of node b, c are same such as "abs" op.
   then b and c can be merged into one node to avoid duplicated computation
"""

from collections import defaultdict, namedtuple

from tf2onnx.optimizer.optimizer_base import GraphOptimizerBase


# pylint: disable=logging-not-lazy,unused-argument,missing-docstring

_KeyToGroupNodes = namedtuple("key", "type input")


class MergeDuplicatedNodesOptimizer(GraphOptimizerBase):
    """Remove duplicate nodes.
    """
    def __init__(self, debug=False):
        super(MergeDuplicatedNodesOptimizer, self).__init__("MergeDuplicatedNodesOptimizer", debug)
        # used internally
        self._graph_can_be_optimized = True

    def _optimize(self, graph):
        return self._apply_optimization(graph, self._optimize_at_current_graph_level)

    def _optimize_at_current_graph_level(self, graph):
        while self._graph_can_be_optimized:
            self._graph_can_be_optimized = False
            self._merge_duplicated_nodes(graph)
        return graph

    def _merge_duplicated_nodes(self, graph):
        # "duplicated" means: op_type, input and attribute are same
        # while attr is un-hashable so doesn't include it when grouping nodes
        nodes_groups = self._group_nodes_by_type_inputs(graph)
        for _, nodes_group in nodes_groups.items():
            if self._skip_node_type(nodes_group[0]):
                continue
            self._del_nodes_if_duplicated(nodes_group, graph)

    @staticmethod
    def _group_nodes_by_type_inputs(graph):
        res = defaultdict(list)
        for node in graph.get_nodes():
            res[_KeyToGroupNodes(node.type, tuple(node.input))].append(node)
        return res

    def _del_nodes_if_duplicated(self, nodes_group, graph):
        # input and op type of nodes in same group are same,
        # and if their attributes are also same then they are duplicated
        while len(nodes_group) > 1:
            unprocessed_node = []
            nodes_to_process = [nodes_group[0]]
            for node in nodes_group[1:]:
                if node.attr == nodes_to_process[0].attr:
                    nodes_to_process.append(node)
                else:
                    unprocessed_node.append(node)

            self._merge_nodes_that_are_duplicated(nodes_to_process, graph)
            nodes_group = unprocessed_node

    def _merge_nodes_that_are_duplicated(self, nodes_to_process, graph):
        # node's output may not all be used, so have to select the one that uses most of node's outputs
        nodes_to_process.sort(key=self._len_of_node_output, reverse=True)
        node_to_retain = nodes_to_process[0]
        for node_to_delete in nodes_to_process[1:]:
            # if one of the output is graph's output then it can't be deleted
            if set(node_to_delete.output).intersection(set(graph.outputs)):
                continue
            for old_input, new_input in zip(node_to_delete.output, node_to_retain.output):
                graph.replace_all_inputs(graph.get_nodes(), old_input, new_input)
            graph.remove_node(node_to_delete.name)
            self._graph_can_be_optimized = True

    @staticmethod
    def _skip_node_type(node):
        # identity node will be handled by identity optimizer so skip it
        if node.type in ["Identity"]:
            return True
        if node.is_graph_input():
            return True
        return False

    @staticmethod
    def _len_of_node_output(node):
        return len(node.output)
