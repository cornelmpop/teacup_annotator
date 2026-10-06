"""Known-bug regressions for turtle-shell boundary path selection."""

from __future__ import annotations

import unittest

from annotator.geom.graph import build_existing_polygon_graph
from annotator.geom.graph import existing_polygon_graph_path
from annotator.geom.graph import existing_polygon_graph_paths


class TurtleShellBoundaryPathRegressionTests(unittest.TestCase):
    """Autoclose paths use the exposed boundary of existing polygons."""

    def test_known_bug_regression_closing_path_excludes_shared_edge(self) -> None:
        """Known-bug regression: Adler2002_403_0_9 must not cross an owned edge."""

        left = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        right = [(10.0, 0.0), (20.0, 0.0), (20.0, 10.0), (10.0, 10.0)]
        graph = build_existing_polygon_graph([left, right], 0.01)

        path = existing_polygon_graph_path(
            graph,
            (10.0, 0.0),
            (10.0, 10.0),
            0.01,
        )

        self.assertIsNotNone(path)
        self.assertGreater(len(path or []), 2)
        traversed_edges = {
            frozenset((start, end))
            for start, end in zip(path or [], (path or [])[1:])
        }
        self.assertNotIn(
            frozenset(((10.0, 0.0), (10.0, 10.0))),
            traversed_edges,
        )

    def test_known_bug_regression_exposes_next_shortest_path(self) -> None:
        """Known-bug regression.

        turtle_shell_autoclose_stops_after_overlapping_shortest_path_2026-08-27
        """

        polygon = [
            (0.0, 0.0),
            (1.0, 0.0),
            (2.0, 0.0),
            (2.0, 2.0),
            (0.0, 2.0),
        ]
        graph = build_existing_polygon_graph([polygon], 0.01)

        paths = list(
            existing_polygon_graph_paths(
                graph,
                (2.0, 0.0),
                (0.0, 0.0),
                0.01,
            )
        )

        self.assertEqual(
            paths,
            [
                [(2.0, 0.0), (1.0, 0.0), (0.0, 0.0)],
                [(2.0, 0.0), (2.0, 2.0), (0.0, 2.0), (0.0, 0.0)],
            ],
        )


if __name__ == "__main__":
    unittest.main()
