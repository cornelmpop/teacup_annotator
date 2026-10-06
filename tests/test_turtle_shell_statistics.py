"""Tests for deriving turtle-shell benchmark intervals from audit rows."""

from __future__ import annotations

import json
import unittest

from annotator.log.audit import CLOSE_AUDIT_ACTION
from annotator.log.audit import VIEW_AUDIT_ACTION
from annotator.log.turtle_shell_statistics import ActiveTurtleShell
from annotator.log.turtle_shell_statistics import CompletedTurtleShell
from annotator.log.turtle_shell_statistics import audit_event_start_ms
from annotator.log.turtle_shell_statistics import audit_event_time_ms
from annotator.log.turtle_shell_statistics import completed_turtle_shell_durations_ms
from annotator.log.turtle_shell_statistics import completed_shell
from annotator.log.turtle_shell_statistics import completed_turtle_shells
from annotator.log.turtle_shell_statistics import created_annotation_polygon
from annotator.log.turtle_shell_statistics import is_turtle_shell_component
from annotator.log.turtle_shell_statistics import polygon_intersects_shell
from annotator.log.turtle_shell_statistics import shell_duration_ms


def create_event(
    event_time: int,
    duration_ms: int,
    annotation_uuid: str,
    polygon: list[tuple[float, float]],
    autoclose: bool = True,
    image_name: str = "image.jpg",
) -> dict[str, object]:
    """Return one create-annotation audit row with audited geometry."""

    return {
        "audit_event_id": event_time,
        "event_time": event_time,
        "duration_ms": duration_ms,
        "action": "create_annotation",
        "source_uuid": annotation_uuid,
        "details_json": json.dumps(
            {"image_name": image_name, "autoclose": autoclose}
        ),
        "after_state_json": json.dumps(
            {
                "image_name": image_name,
                "annotations": [
                    {
                        "annotation_uuid": annotation_uuid,
                        "polygon_coords": polygon,
                    }
                ],
            }
        ),
    }


class TurtleShellStatisticsTests(unittest.TestCase):
    """Completed-shell timing follows audit event boundaries."""

    def test_event_helpers_extract_shell_component_timing_and_geometry(
        self,
    ) -> None:
        """Shell helper functions expose the audited row fields directly."""

        polygon = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        event = create_event(1_500, 500, "ann:1", polygon)
        shell = ActiveTurtleShell(
            image_name="image.jpg",
            start_ms=1_000,
            last_activity_ms=1_500,
            polygons=[polygon],
        )

        self.assertTrue(is_turtle_shell_component(event))
        self.assertEqual(created_annotation_polygon(event), polygon)
        self.assertEqual(audit_event_time_ms(event), 1_500)
        self.assertEqual(audit_event_start_ms(event), 1_000)
        self.assertEqual(shell_duration_ms(shell, 2_000), 1_000)
        self.assertEqual(completed_shell(shell, 2_000), CompletedTurtleShell(1_000, 1))
        self.assertTrue(
            polygon_intersects_shell(
                [(10.0, 0.0), (20.0, 0.0), (20.0, 10.0), (10.0, 10.0)],
                shell.polygons,
            )
        )
        self.assertFalse(
            polygon_intersects_shell(
                [
                    (100.0, 100.0),
                    (110.0, 100.0),
                    (110.0, 110.0),
                    (100.0, 110.0),
                ],
                shell.polygons,
            )
        )

    def test_connected_shell_components_complete_on_close(self) -> None:
        """Connected autoclose components form one shell until app close."""

        events = [
            create_event(
                1_500,
                500,
                "ann:1",
                [(0, 0), (10, 0), (10, 10), (0, 10)],
            ),
            create_event(
                3_200,
                200,
                "ann:2",
                [(10, 0), (20, 0), (20, 10), (10, 10)],
            ),
            {
                "audit_event_id": 3,
                "event_time": 4_000,
                "action": CLOSE_AUDIT_ACTION,
                "details_json": "{}",
            },
        ]

        self.assertEqual(completed_turtle_shell_durations_ms(events), [3_000])

    def test_known_bug_regression_records_final_polygon_count(self) -> None:
        """Known-bug regression: completed-shell stats retain component count."""

        events = [
            create_event(
                1_500,
                500,
                "ann:1",
                [(0, 0), (10, 0), (10, 10), (0, 10)],
            ),
            create_event(
                3_200,
                200,
                "ann:2",
                [(10, 0), (20, 0), (20, 10), (10, 10)],
            ),
            {
                "audit_event_id": 3,
                "event_time": 4_000,
                "action": CLOSE_AUDIT_ACTION,
                "details_json": "{}",
            },
        ]

        self.assertEqual(
            completed_turtle_shells(events),
            [CompletedTurtleShell(duration_ms=3_000, final_polygon_count=2)],
        )

    def test_known_bug_regression_long_active_edit_is_not_idle(self) -> None:
        """Known-bug regression turtle_shell_statistics_counts_timed_edits_as_idle_2026-08-27."""

        events = [
            create_event(
                1_500,
                500,
                "ann:1",
                [(0, 0), (10, 0), (10, 10), (0, 10)],
            ),
            create_event(
                13_000,
                11_000,
                "ann:2",
                [(10, 0), (20, 0), (20, 10), (10, 10)],
            ),
            {
                "audit_event_id": 3,
                "event_time": 13_500,
                "action": CLOSE_AUDIT_ACTION,
                "details_json": "{}",
            },
        ]

        self.assertEqual(
            completed_turtle_shells(events),
            [CompletedTurtleShell(duration_ms=12_500, final_polygon_count=2)],
        )

    def test_true_between_edit_idle_gap_still_completes_shell(self) -> None:
        """True idle time between completed edits remains a shell boundary."""

        events = [
            create_event(
                1_500,
                500,
                "ann:1",
                [(0, 0), (10, 0), (10, 10), (0, 10)],
            ),
            create_event(
                12_100,
                100,
                "ann:2",
                [(10, 0), (20, 0), (20, 10), (10, 10)],
            ),
            {
                "audit_event_id": 3,
                "event_time": 13_000,
                "action": CLOSE_AUDIT_ACTION,
                "details_json": "{}",
            },
        ]

        self.assertEqual(
            completed_turtle_shells(events),
            [
                CompletedTurtleShell(duration_ms=500, final_polygon_count=1),
                CompletedTurtleShell(duration_ms=1_000, final_polygon_count=1),
            ],
        )

    def test_unrelated_annotation_starts_a_new_shell_boundary(self) -> None:
        """A disconnected creation ends the active shell at its start time."""

        events = [
            create_event(
                1_500,
                500,
                "ann:1",
                [(0, 0), (10, 0), (10, 10), (0, 10)],
            ),
            create_event(
                4_200,
                200,
                "ann:2",
                [(100, 100), (110, 100), (110, 110), (100, 110)],
            ),
            {
                "audit_event_id": 3,
                "event_time": 5_000,
                "action": CLOSE_AUDIT_ACTION,
                "details_json": "{}",
            },
        ]

        self.assertEqual(
            completed_turtle_shell_durations_ms(events),
            [3_000, 1_000],
        )

    def test_image_change_completes_active_shell(self) -> None:
        """A view event for another image closes the shell immediately."""

        events = [
            create_event(
                1_500,
                500,
                "ann:1",
                [(0, 0), (10, 0), (10, 10), (0, 10)],
            ),
            {
                "audit_event_id": 2,
                "event_time": 2_000,
                "action": VIEW_AUDIT_ACTION,
                "details_json": json.dumps({"image_name": "next.jpg"}),
            },
        ]

        self.assertEqual(completed_turtle_shell_durations_ms(events), [1_000])

    def test_idle_gap_subtracts_the_idle_timeout(self) -> None:
        """Ten seconds with no audit rows ends the shell at last activity."""

        events = [
            create_event(
                1_500,
                500,
                "ann:1",
                [(0, 0), (10, 0), (10, 10), (0, 10)],
            ),
            {
                "audit_event_id": 2,
                "event_time": 20_000,
                "action": "change_class",
                "details_json": "{}",
            },
        ]

        self.assertEqual(completed_turtle_shell_durations_ms(events), [500])

    def test_current_time_can_complete_idle_open_shell(self) -> None:
        """The live CSV can include shells idle before another event exists."""

        events = [
            create_event(
                1_500,
                500,
                "ann:1",
                [(0, 0), (10, 0), (10, 10), (0, 10)],
            )
        ]

        self.assertEqual(
            completed_turtle_shell_durations_ms(events, current_time_ms=12_000),
            [500],
        )
        self.assertEqual(
            completed_turtle_shell_durations_ms(events, current_time_ms=3_000),
            [],
        )


if __name__ == "__main__":
    unittest.main()
