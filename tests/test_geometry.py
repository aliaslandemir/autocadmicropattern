import math
import unittest
from dataclasses import replace

import numpy as np
from numpy.testing import assert_allclose

from geometry import (
    PatternParameters, generate_hex_grid, orientation_angles,
    orientation_angle_1_defect, orientation_angle_2_defects, shape_vertices,
)


class GeometryTests(unittest.TestCase):
    def test_grid_matches_original_order_and_coordinates(self):
        for radius in (0, 1, 3, 9, 25):
            q, r = np.meshgrid(range(-radius, radius+1), range(-radius, radius+1))
            mask = np.abs(q+r) <= radius
            expected = np.column_stack((1.5*16*q[mask], np.sqrt(3)*16*(r[mask]+0.5*q[mask])))
            actual = generate_hex_grid(radius, 16)
            assert_allclose(actual, expected)
            self.assertEqual(len(actual), 1+3*radius*(radius+1))
            self.assertEqual(len(np.unique(actual, axis=0)), len(actual))
            assert_allclose(actual.mean(axis=0), [0, 0], atol=1e-12)

    def test_vectorized_angles_preserve_both_formulas(self):
        centers = generate_hex_grid(3, 2)
        for count in (1, 2):
            params = PatternParameters(one_or_two=count, theta0=45, m=-0.5)
            if count == 1:
                expected = [orientation_angle_1_defect(c, params.defect1, math.pi/4, params.m) for c in centers]
            else:
                expected = [orientation_angle_2_defects(c, (params.defect1, params.defect2), math.pi/4) for c in centers]
            assert_allclose(orientation_angles(centers, params), expected)

    def test_rectangle_rotation_and_center(self):
        params = PatternParameters(rect_w=4, rect_h=2)
        centers = np.array([[10, 20]])
        vertices = shape_vertices(centers, np.array([math.pi/2]), params)
        assert_allclose(vertices[0], [[11, 18], [11, 22], [9, 22], [9, 18]])
        assert_allclose(vertices.mean(axis=1), centers)

    def test_triangle_is_equilateral_and_centroid_is_center(self):
        params = PatternParameters(shape_type="triangle", triangle_edge=12)
        centers = generate_hex_grid(2, 16)
        vertices = shape_vertices(centers, orientation_angles(centers, params), params)
        assert_allclose(vertices.mean(axis=1), centers, atol=1e-12)
        edges = np.roll(vertices, -1, axis=1) - vertices
        assert_allclose(np.linalg.norm(edges, axis=2), 12)

    def test_invalid_values_are_rejected(self):
        invalid = [dict(radius=-1), dict(radius=101), dict(radius=1.5), dict(radius=True),
                   dict(side_length=0), dict(side_length=float("nan")), dict(side_length=float("inf")),
                   dict(rect_w=-1), dict(theta0=float("nan")), dict(m=float("inf")),
                   dict(defect1=None), dict(defect1=(0, float("nan"))),
                   dict(one_or_two=2, defect2=(float("inf"), 1)), dict(one_or_two=3),
                   dict(circle_r=-1), dict(circle_r2=float("nan")),
                   dict(shape_type="triangle", triangle_edge=0),
                   dict(shape_type="circle", shape_circle_r=-1), dict(shape_type="unknown"),
                   dict(side_length=1e308), dict(m=1e308), dict(circle_r=1e308),
                   dict(defect1=(1e308, 1e308)), dict(rect_w=1e308)]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(PatternParameters(), **changes).validate()

    def test_unused_fields_are_not_required(self):
        params = PatternParameters(shape_type="triangle", rect_w=float("nan"),
                                   rect_h=-1, shape_circle_r=-1, defect2=None)
        self.assertIs(params.validate(), params)

    def test_center_rings_skip_zero_and_duplicates(self):
        self.assertEqual(PatternParameters().center_circle_radii, (45,))
        self.assertEqual(PatternParameters(circle_r=0, circle_r2=0).center_circle_radii, ())
        self.assertEqual(PatternParameters(circle_r=10, circle_r2=20).center_circle_radii, (10, 20))

    def test_radius_limit(self):
        self.assertEqual(generate_hex_grid(100, 1).shape, (30301, 2))


if __name__ == "__main__":
    unittest.main()
