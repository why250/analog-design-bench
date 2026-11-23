"""Independent conforming FEM checks with analytic and concave-domain controls."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from dc_fem import FEMError, analyze_export, make_mesh, solve_fem, validate_mesh
from dc_resistance import Contact, locate_contact
from plot_geometry import Pin, Polygon, Port


def rectangle(length=10, width=2):
    points = ((0, 0), (length, 0), (length, width), (0, width))
    contacts = [locate_contact(points, Pin("P1", "P1", 35, 0, width / 2), width),
                locate_contact(points, Pin("P2", "P2", 35, length, width / 2), width)]
    return points, contacts


def u_shape():
    points = ((0, 0), (2, 0), (2, 8), (8, 8), (8, 0), (10, 0), (10, 10), (0, 10))
    contacts = [locate_contact(points, Pin("P1", "P1", 35, 1, 0), 2),
                locate_contact(points, Pin("P2", "P2", 35, 9, 0), 2)]
    return points, contacts


class FEMTests(unittest.TestCase):
    def test_rectangle_matches_analytic_R_and_independent_power_at_three_meshes(self):
        points, contacts = rectangle()
        for h in (0.5, 0.25, 0.125):
            result = solve_fem(points, contacts, 2, 0.5, h)
            self.assertAlmostEqual(result.metrics["R_ohm"], 5, places=9)
            self.assertLess(result.metrics["relative_terminal_current_imbalance"], 1e-9)
            self.assertLess(result.metrics["relative_independent_power_error"], 1e-9)
            self.assertLess(result.metrics["relative_free_node_residual"], 1e-9)
            self.assertAlmostEqual(result.metrics["element_dissipation_W"], 0.2, places=10)
            validation = result.mesh.validation
            self.assertEqual(validation["missing_boundary_segments"], 0)
            self.assertEqual(validation["extra_boundary_segments"], 0)
            self.assertAlmostEqual(validation["triangle_area_um2"], 20)
            self.assertEqual(validation["Euler_V_minus_E_plus_T"], 1)
            self.assertEqual(validation["triangle_edge_connected_components"], 1)

    def test_rotated_rectangle_is_not_a_square_cell_operator(self):
        points, contacts = rectangle()
        angle = np.deg2rad(31)
        rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
        rotated = np.asarray(points) @ rotation.T + [7.4, -3.2]
        transformed = [Contact(c.name, tuple(np.asarray(c.start) @ rotation.T + [7.4, -3.2]),
                               tuple(np.asarray(c.end) @ rotation.T + [7.4, -3.2]),
                               tuple(np.asarray(c.inward_normal) @ rotation.T), 0) for c in contacts]
        result = solve_fem(rotated, transformed, 1, 1, 0.25)
        self.assertAlmostEqual(result.metrics["R_ohm"], 5, places=9)
        self.assertAlmostEqual(result.mesh.validation["triangle_area_um2"], 20, places=10)

    def test_sigma_thickness_scaling_and_terminal_interchange(self):
        points, contacts = rectangle()
        nominal = solve_fem(points, contacts, 2, 0.5, 0.5)
        sigma = solve_fem(points, contacts, 4, 0.5, 0.5)
        thickness = solve_fem(points, contacts, 2, 1, 0.5)
        reverse = solve_fem(points, list(reversed(contacts)), 2, 0.5, 0.5)
        self.assertAlmostEqual(nominal.metrics["R_ohm"] / sigma.metrics["R_ohm"], 2)
        self.assertAlmostEqual(nominal.metrics["R_ohm"] / thickness.metrics["R_ohm"], 2)
        self.assertAlmostEqual(nominal.metrics["R_ohm"], reverse.metrics["R_ohm"], places=10)
        np.testing.assert_allclose(nominal.voltage_V + reverse.voltage_V, 1, atol=1e-11)

    def test_concave_U_area_gap_and_observed_refinement(self):
        points, contacts = u_shape()
        results = [solve_fem(points, contacts, 1, 1, h) for h in (0.5, 0.25, 0.125)]
        for result in results:
            self.assertAlmostEqual(result.mesh.validation["triangle_area_um2"], 52)
            self.assertGreater(result.metrics["R_ohm"], 10)
            centroids = result.mesh.vertices_um[result.mesh.triangles].mean(axis=1)
            self.assertFalse(np.any((centroids[:, 0] > 2) & (centroids[:, 0] < 8) & (centroids[:, 1] < 8)))
        first = abs(results[1].metrics["R_ohm"] - results[0].metrics["R_ohm"])
        second = abs(results[2].metrics["R_ohm"] - results[1].metrics["R_ohm"])
        # This deterministic control exhibits convergence; the tool does not
        # assume monotonicity or use the last difference as an error bound.
        self.assertLess(second, first)
        self.assertLess(second / results[2].metrics["R_ohm"], 0.005)

    def test_octagonal_C_with_two_full_ten_um_terminal_edges(self):
        points = ((-1,-35),(-11,-35),(-11,-30),(-20,-30),(-30,-20),(-30,20),(-20,30),(20,30),
                  (30,20),(30,-20),(20,-30),(11,-30),(11,-35),(1,-35),(1,-20),(15,-20),
                  (20,-15),(20,15),(15,20),(-15,20),(-20,15),(-20,-15),(-15,-20),(-1,-20))
        contacts = [locate_contact(points, Pin("P1", "P1", 35, -6, -35), 10),
                    locate_contact(points, Pin("P2", "P2", 35, 6, -35), 10)]
        result = solve_fem(points, contacts, 2.405e7, 9.9e-7, 0.5)
        self.assertGreater(result.metrics["R_ohm"], 0)
        self.assertEqual(result.metrics["contact_widths_um"], [10, 10])
        self.assertEqual(result.mesh.validation["missing_boundary_segments"], 0)
        self.assertEqual(result.mesh.validation["extra_boundary_segments"], 0)
        self.assertLess(result.mesh.validation["absolute_area_difference_um2"], 1e-8)

    def test_clockwise_polygon_preserves_result(self):
        points, contacts = u_shape()
        a = solve_fem(points, contacts, 1, 1, 0.5)
        b = solve_fem(tuple(reversed(points)), contacts, 1, 1, 0.5)
        self.assertAlmostEqual(a.metrics["R_ohm"], b.metrics["R_ohm"], places=8)

    def test_floating_point_collinear_diagonal_artifacts_do_not_change_boundary(self):
        points = ((0,0),(2,0),(2,6),(4,8),(8,8),(10,6),(10,0),(12,0),(12,7),(9,10),(3,10),(0,7))
        mesh = make_mesh(points,0.5)
        self.assertEqual(mesh.validation["missing_boundary_segments"],0)
        self.assertEqual(mesh.validation["extra_boundary_segments"],0)
        self.assertLess(mesh.validation["removed_boundary_artifact_absolute_area_um2"],1e-10)
        self.assertFalse(mesh.validation["geometry_jitter"])

    def test_missing_or_extra_conforming_boundary_is_rejected(self):
        points, _ = rectangle()
        mesh = make_mesh(points, 0.5)
        with self.assertRaisesRegex(FEMError, "boundary recovery"):
            validate_mesh(mesh.vertices_um, mesh.triangles, np.asarray(points), mesh.required_boundary_edges[:-1], 1e-9)
        extra = np.vstack((mesh.required_boundary_edges, [0, 2]))
        with self.assertRaisesRegex(FEMError, "boundary recovery"):
            validate_mesh(mesh.vertices_um, mesh.triangles, np.asarray(points), extra, 1e-9)
        with self.assertRaises(FEMError):
            validate_mesh(mesh.vertices_um, mesh.triangles[:-1], np.asarray(points), mesh.required_boundary_edges, 1e-9)

    def test_self_intersection_or_zero_width_connector_is_rejected(self):
        with self.assertRaises(FEMError):
            make_mesh(((0,0),(4,4),(0,4),(4,0)), 0.5)
        with self.assertRaises(FEMError):
            make_mesh(((0,0),(2,0),(2,2),(0,2),(0,0),(4,0),(6,0),(6,2),(4,2),(4,0)), 0.5)

    def test_unreasonably_small_mesh_rejects_before_point_allocation(self):
        points, _ = rectangle()
        with self.assertRaisesRegex(FEMError,"safety limit"):
            make_mesh(points,1e-300)

    def test_partial_contact_or_shared_contact_vertex_is_rejected(self):
        points, contacts = rectangle()
        partial = Contact("P1", (0,0.5), (0,1.5), (1,0), 0)
        with self.assertRaisesRegex(FEMError, "complete polygon edge"):
            solve_fem(points, [partial, contacts[1]], 1, 1, 0.125)
        bottom = Contact("P2", (0,0), (10,0), (0,1), 0)
        with self.assertRaisesRegex(FEMError, "overlap or touch"):
            solve_fem(points, [contacts[0], bottom], 1, 1, 0.25)

    def test_export_receipt_is_fresh_finite_and_retains_fixed_contact_and_mesh(self):
        points, _ = rectangle(20, 10)
        ports = (Port(1,"P1",("P1",),("P4",),50,0),Port(2,"P2",("P2",),("P4",),50,0))
        pins = (Pin("P1","P1",35,0,5),Pin("P2","P2",35,20,5),Pin("P4","P4",7,0,-10))
        ltd = """UNITS
DISTANCE=METRE
CONDUCTIVITY=SIEMENS/M
END_UNITS
MATERIAL Metal6 CONDUCTIVITY=2.405e7 IMAG_CONDUCTIVITY=0 PERMEABILITY=1
OPERATION Thickness EXPAND=9.9e-7 UP
MASK 35 Name=Metal6 MATERIAL=Metal6 OPERATION=Thickness
"""
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "deck"
            source.mkdir()
            for name in ("proj_a", "proj.pin", "proj.prt"):
                (source/name).write_text("synthetic reader fixture", encoding="utf-8")
            (source/"proj.ltd").write_text(ltd,encoding="utf-8")
            output = Path(temporary) / "fem"
            with patch("dc_fem.read_export", return_value=((Polygon(35,points),),pins,ports)):
                report = analyze_export(source,output,(1,0.5),plots=False)
                self.assertEqual(report["device_target_result"],"NOT_EVALUATED")
                self.assertFalse(report["contact_model_changed_or_fitted"])
                self.assertEqual(len(report["sources"]),4)
                self.assertTrue((output/"dc-fem-analysis.json").is_file())
                self.assertTrue((output/"dc-fem-finest-mesh.npz").is_file())
                json.dumps(report,allow_nan=False)
                with self.assertRaises(FileExistsError):
                    analyze_export(source,output,(1,0.5),plots=False)


if __name__ == "__main__":
    unittest.main()
