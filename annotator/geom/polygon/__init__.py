"""Public polygon-geometry API for editing, snapping, rendering, and COCO I/O."""

from __future__ import annotations

from annotator.geom.polygon.editing import polygon_has_unshared_vertex
from annotator.geom.polygon.editing import polygon_is_non_degenerate
from annotator.geom.polygon.editing import polygon_with_inserted_edge_vertices
from annotator.geom.polygon.editing import reorder_polygon_start_clockwise
from annotator.geom.polygon.metrics import area
from annotator.geom.polygon.metrics import bbox
from annotator.geom.polygon.metrics import bbox_for_polygon
from annotator.geom.polygon.metrics import outward_vertex_normal
from annotator.geom.polygon.metrics import point_in_polygon
from annotator.geom.polygon.metrics import polygon_area
from annotator.geom.polygon.metrics import polygon_centroid
from annotator.geom.polygon.metrics import polygon_distance_to_point
from annotator.geom.polygon.metrics import polygon_intersects_box
from annotator.geom.polygon.metrics import signed_polygon_area
from annotator.geom.polygon.overlaps import overlapping_polygon_edge_segments
from annotator.geom.polygon.overlaps import (
    overlapping_polygon_edge_segments_between,
)
from annotator.geom.polygon.overlaps import overlapping_polygon_vertices
from annotator.geom.polygon.resampling import arrow_polygon_boundary_start
from annotator.geom.polygon.resampling import closed_ring_perimeter
from annotator.geom.polygon.resampling import point_on_closed_ring_at_distance
from annotator.geom.polygon.resampling import polygon_outer_outline
from annotator.geom.polygon.resampling import remove_close_polygon_vertices
from annotator.geom.polygon.resampling import resample_closed_polygon
from annotator.geom.polygon.resampling import rotate_closed_ring_to_start
from annotator.geom.polygon.resampling import simplify_closed_polygon_imai_iri
from annotator.geom.polygon.resampling import simplify_closed_polygon_rdp
from annotator.geom.polygon.resampling import simplify_closed_polygon_visvalingam
from annotator.geom.polygon.resampling import simplify_polygon_outline
from annotator.geom.polygon.snapping import existing_polygon_vertex_path
from annotator.geom.polygon.snapping import nearest_snap_point_on_polygon_edges
from annotator.geom.polygon.union import shapely_polygon_exterior
from annotator.geom.polygon.union import single_polygon_list
from annotator.geom.polygon.union import polygonal_geometry

__all__ = [
    "area",
    "arrow_polygon_boundary_start",
    "bbox",
    "bbox_for_polygon",
    "closed_ring_perimeter",
    "existing_polygon_vertex_path",
    "nearest_snap_point_on_polygon_edges",
    "outward_vertex_normal",
    "overlapping_polygon_edge_segments",
    "overlapping_polygon_edge_segments_between",
    "overlapping_polygon_vertices",
    "point_in_polygon",
    "point_on_closed_ring_at_distance",
    "polygon_area",
    "polygon_centroid",
    "polygon_distance_to_point",
    "polygon_has_unshared_vertex",
    "polygon_intersects_box",
    "polygon_is_non_degenerate",
    "polygon_outer_outline",
    "polygon_with_inserted_edge_vertices",
    "remove_close_polygon_vertices",
    "reorder_polygon_start_clockwise",
    "resample_closed_polygon",
    "rotate_closed_ring_to_start",
    "shapely_polygon_exterior",
    "signed_polygon_area",
    "simplify_closed_polygon_imai_iri",
    "simplify_closed_polygon_rdp",
    "simplify_closed_polygon_visvalingam",
    "simplify_polygon_outline",
    "single_polygon_list",
    "polygonal_geometry",
]
