"""CODEX: Build and query exposed polygon-boundary graphs.

CODEX: Graph nodes represent canonical existing vertices after
CODEX: tolerance-based coalescing. Undirected edges follow closed polygon
CODEX: outlines, but an edge owned by more than one source polygon is omitted
CODEX: so Turtle-shell paths follow exposed boundaries rather than internal
CODEX: shared edges.

CODEX: A uniform-grid spatial index supports nearby-node lookup. Single-path
CODEX: callers receive the shortest exposed route, while autoclose can iterate
CODEX: simple paths in increasing geometric length and stop at the first
CODEX: non-overlapping candidate. GUI code owns graph caching, invalidation,
CODEX: overlap rejection, and temporary edge insertion. These helpers do not
CODEX: mutate source polygons.
"""

from __future__ import annotations

from collections.abc import Iterator
import heapq
import math
from typing import Any

def build_existing_polygon_graph(
    polygons: list[list[tuple[float, float]]],
    tolerance: float,
) -> dict[str, Any]:
    """Return a reusable exposed-boundary graph for existing polygons.

    Process polygons and vertices in input order. A vertex reuses the first
    encountered stored node within `tolerance`; otherwise its exact coordinates
    become a new canonical node. A uniform grid narrows matching to nodes in the
    point's cell and its eight adjacent cells.

    Treat every polygon with at least two vertices as closed, adding undirected
    edges between consecutive vertices and from the final vertex back to the
    first. Ignore edges whose endpoints collapse to one canonical node and count
    a repeated edge only once per source polygon. Retain an edge only when
    exactly one polygon owns it; edges shared by multiple polygons are interior
    seams and are not walkable.

    The returned dictionary contains canonical `nodes`, parallel adjacency sets
    in `edges`, the `nodes_by_cell` spatial index, and `cell_size`. A negative
    tolerance returns an empty graph. A zero tolerance merges only coincident
    vertices while retaining a nonzero cell size for safe arithmetic.
    """

    # Keep spatial arithmetic defined at zero; a negative tolerance disables below.
    cell_size = max(tolerance, 1e-9)
    nodes: list[tuple[float, float]] = []
    edges: list[set[int]] = []
    nodes_by_cell: dict[tuple[int, int], list[int]] = {}
    edge_owners: dict[tuple[int, int], set[int]] = {}

    def cell_key(point: tuple[float, float]) -> tuple[int, int]:
        """Return the uniform-grid cell containing `point`."""

        return math.floor(point[0] / cell_size), math.floor(point[1] / cell_size)

    def neighboring_cell_keys(point: tuple[float, float]) -> list[tuple[int, int]]:
        """Return the point's cell and its eight adjacent cells in scan order."""

        base_x, base_y = cell_key(point)
        return [
            (base_x + offset_x, base_y + offset_y)
            for offset_x in (-1, 0, 1)
            for offset_y in (-1, 0, 1)
        ]

    def node_for(point: tuple[float, float]) -> int:
        """Return a matching canonical node, or append one for `point`."""

        for key in neighboring_cell_keys(point):
            for node_index in nodes_by_cell.get(key, []):
                if math.dist(point, nodes[node_index]) <= tolerance:
                    return node_index
        node_index = len(nodes)
        nodes.append(point)
        edges.append(set())
        nodes_by_cell.setdefault(cell_key(point), []).append(node_index)
        return node_index

    # Negative tolerance explicitly disables graph construction.
    if tolerance < 0:
        return {
            "nodes": nodes,
            "edges": edges,
            "nodes_by_cell": nodes_by_cell,
            "cell_size": cell_size,
        }
    for polygon_index, polygon in enumerate(polygons):
        if len(polygon) < 2:
            continue
        polygon_nodes = [node_for(point) for point in polygon]
        polygon_edges: set[tuple[int, int]] = set()
        # Treat each outline as closed and count each undirected edge once per polygon.
        for index, node_index in enumerate(polygon_nodes):
            next_index = polygon_nodes[(index + 1) % len(polygon_nodes)]
            if node_index == next_index:
                continue
            polygon_edges.add(tuple(sorted((node_index, next_index))))
        for edge in polygon_edges:
            edge_owners.setdefault(edge, set()).add(polygon_index)
    # Shared edges are interior seams; boundary paths may use only exposed edges.
    for (start_index, end_index), owners in edge_owners.items():
        if len(owners) != 1:
            continue
        edges[start_index].add(end_index)
        edges[end_index].add(start_index)
    return {
        "nodes": nodes,
        "edges": edges,
        "nodes_by_cell": nodes_by_cell,
        "cell_size": cell_size,
    }


def existing_polygon_graph_path(
    graph: dict[str, Any],
    start_point: tuple[float, float],
    target_point: tuple[float, float],
    tolerance: float,
) -> list[tuple[float, float]] | None:
    """CODEX: Return the shortest exposed-boundary path between nearby graph nodes.

    CODEX: This is the single-path convenience wrapper for callers that do not
    CODEX: need overlap-aware alternatives.
    """

    for path in existing_polygon_graph_paths(
        graph,
        start_point,
        target_point,
        tolerance,
    ):
        return path
    return None


def existing_polygon_graph_paths(
    graph: dict[str, Any],
    start_point: tuple[float, float],
    target_point: tuple[float, float],
    tolerance: float,
) -> Iterator[list[tuple[float, float]]]:
    """CODEX: Yield exposed-boundary paths in increasing geometric length.

    CODEX: Polygon creation stores snapped coordinates, not graph node IDs, so
    CODEX: endpoints are resolved through ``nearest_graph_node`` before
    CODEX: routing. The enumerator uses uniform-cost search over simple paths:
    CODEX: heap entries carry the complete node path, and the next completed
    CODEX: path popped from the heap is yielded before longer paths.

    CODEX: This approach was chosen over removing every edge from a rejected
    CODEX: shortest path because valid alternatives can share part of that
    CODEX: rejected path. It was chosen over enumerating and sorting all paths
    CODEX: upfront because autoclose normally accepts an early candidate and
    CODEX: should not materialize the whole finite path set first. Equal-length
    CODEX: paths follow graph node-index order through the heap tuple.
    """

    nodes: list[tuple[float, float]] = graph["nodes"]
    edges: list[set[int]] = graph["edges"]
    start_index = nearest_graph_node(graph, start_point, tolerance)
    target_index = nearest_graph_node(graph, target_point, tolerance)
    if start_index is None or target_index is None:
        return
    if start_index == target_index:
        yield [nodes[start_index]]
        return

    queue_items: list[tuple[float, tuple[int, ...]]] = [(0.0, (start_index,))]
    while queue_items:
        distance, path_indices = heapq.heappop(queue_items)
        node_index = path_indices[-1]
        if node_index == target_index:
            yield [nodes[index] for index in path_indices]
            continue
        used_indices = set(path_indices)
        for neighbour_index in sorted(edges[node_index]):
            if neighbour_index in used_indices:
                continue
            next_distance = distance + math.dist(
                nodes[node_index], nodes[neighbour_index]
            )
            next_path = (*path_indices, neighbour_index)
            heapq.heappush(queue_items, (next_distance, next_path))


def nearest_graph_node(
    graph: dict[str, Any],
    point: tuple[float, float],
    tolerance: float,
) -> int | None:
    """Return the nearest canonical graph-node index within `tolerance`.

    Search node indices recorded for the point's uniform-grid cell and its eight
    adjacent cells using the graph's stored `cell_size`. Callers should use the
    graph-construction tolerance; a larger query radius may extend beyond those
    inspected cells.

    Candidates exactly at the tolerance boundary qualify. When candidates are
    equidistant, the later candidate in cell scan order wins. Return `None` when
    no candidate qualifies, including for a negative tolerance. The graph is
    not mutated.
    """

    nodes: list[tuple[float, float]] = graph["nodes"]
    nodes_by_cell: dict[tuple[int, int], list[int]] = graph["nodes_by_cell"]
    cell_size = float(graph["cell_size"])
    base_x = math.floor(point[0] / cell_size)
    base_y = math.floor(point[1] / cell_size)
    best_index: int | None = None
    best_distance = tolerance
    # Adjacent cells cover the tolerance used to construct this spatial index.
    for offset_x in (-1, 0, 1):
        for offset_y in (-1, 0, 1):
            cell = base_x + offset_x, base_y + offset_y
            for index in nodes_by_cell.get(cell, []):
                distance = math.dist(point, nodes[index])
                # Either equidistant node is valid; scan order selects the later one.
                if distance <= best_distance:
                    best_index = index
                    best_distance = distance
    return best_index
