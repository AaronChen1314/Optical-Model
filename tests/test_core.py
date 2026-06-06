import unittest

import numpy as np

from app import app
from optics_core.export import result_to_csv
from optics_core.materials import MaterialDatabase, parse_numeric_table
from optics_core.rcwa_engine import generate_shape_masks, run_rcwa
from optics_core.temperature import evaluate_eg, kk_delta_n
from optics_core.tmm_engine import run_tmm


class MaterialTests(unittest.TestCase):
    def test_parse_material_txt_sorts_and_clamps_k(self):
        wl, n, k = parse_numeric_table("600 2.1 -0.2\n500 2.0 0.1\n")
        self.assertEqual(wl.tolist(), [500.0, 600.0])
        self.assertEqual(n.tolist(), [2.0, 2.1])
        self.assertEqual(k.tolist(), [0.1, 0.0])

    def test_parse_material_csv_header(self):
        wl, n, k = parse_numeric_table("wavelength_nm,n,k\n500,2,0.1\n510,2.1,0.2\n")
        self.assertEqual(len(wl), 2)
        self.assertAlmostEqual(float(k[-1]), 0.2)


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.db = MaterialDatabase()

    def test_tmm_all_perovskite_reference_near_rcwa_planar_baseline(self):
        result = run_tmm(
            {"template_id": "all_perovskite_planar_reference", "wavelength": {"start_nm": 300, "stop_nm": 1060, "step_nm": 10}},
            self.db,
        )
        self.assertEqual(result["method"], "tmm")
        self.assertEqual(result["geometry"], "planar")
        self.assertIn("planar multilayer", result["model_note"])
        self.assertTrue(np.isfinite(result["reflection"]).all())
        self.assertIn("matched", result["jsc_mA_cm2"])
        self.assertGreater(result["jsc_mA_cm2"]["matched"], 16.5)
        self.assertLess(result["jsc_mA_cm2"]["matched"], 16.9)
        self.assertIn("layer_currents_mA_cm2", result)
        self.assertGreater(len(result["layer_currents_mA_cm2"]), 8)
        self.assertAlmostEqual(result["active_currents_mA_cm2"]["WBG active layer"], result["jsc_mA_cm2"]["WBG active layer"])

    def test_tmm_perovskite_silicon_returns_finite_result(self):
        result = run_tmm(
            {"template_id": "perovskite_silicon", "wavelength": {"start_nm": 300, "stop_nm": 320, "step_nm": 20}},
            self.db,
        )
        self.assertEqual(len(result["layers"]), 15)
        self.assertIn("matched", result["jsc_mA_cm2"])


class TemperatureTests(unittest.TestCase):
    def test_evaluate_eg_formula(self):
        self.assertAlmostEqual(evaluate_eg("Eg(T)=1.64 - 0.00025*(T-300)", 320), 1.635)

    def test_kk_delta_n_shape(self):
        delta = kk_delta_n(np.array([300.0, 400.0, 500.0]), np.array([0.1, 0.2, 0.1]), np.array([0.12, 0.18, 0.1]))
        self.assertEqual(delta.shape, (3,))
        self.assertTrue(np.isfinite(delta).all())

    def test_temperature_sweep_api_returns_nk_and_jsc(self):
        client = app.test_client()
        response = client.post(
            "/api/temperature/sweep",
            json={
                "template_id": "all_perovskite_planar_reference",
                "layers": [],
                "wavelength": {"start_nm": 300, "stop_nm": 1060, "step_nm": 10},
                "temperature": {
                    "temperatures_K": [300, 320],
                    "reference_K": 300,
                    "bandgap_models": [
                        {"layer_name": "WBG active layer", "material": "wbg_perovskite", "Eg_ref_eV": 1.75, "alpha_eV_per_K": -2.5e-4, "reference_K": 300},
                        {"layer_name": "NBG active layer", "material": "nbg_perovskite", "Eg_ref_eV": 1.25, "alpha_eV_per_K": -2.5e-4, "reference_K": 300},
                    ],
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["jsc_vs_temperature"]), 2)
        self.assertIn("optical_constants", response.json)
        self.assertGreater(response.json["jsc_vs_temperature"][-1]["matched"], 1.0)
        self.assertEqual(len(response.json["bandgap_models"]), 2)
        first_curve = response.json["optical_constants"][0]
        self.assertIn("valid_wavelength_range_nm", first_curve)
        self.assertIn("band_edge_nm", first_curve)
        self.assertTrue(first_curve["temperature_adjusted"])

    def test_temperature_nk_long_wavelength_tail_is_stable(self):
        client = app.test_client()
        response = client.post(
            "/api/temperature/sweep",
            json={
                "template_id": "all_perovskite_planar_reference",
                "wavelength": {"start_nm": 300, "stop_nm": 1060, "step_nm": 2},
                "temperature": {
                    "temperatures_K": [280, 300, 320],
                    "reference_K": 300,
                    "bandgap_models": [
                        {"layer_name": "WBG active layer", "material": "wbg_perovskite", "Eg_ref_eV": 1.75, "alpha_eV_per_K": -2.5e-4, "reference_K": 300},
                        {"layer_name": "NBG active layer", "material": "nbg_perovskite", "Eg_ref_eV": 1.25, "alpha_eV_per_K": -2.5e-4, "reference_K": 300},
                    ],
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        for curve in response.json["optical_constants"]:
            if curve["temperature_K"] not in (280.0, 320.0):
                continue
            wl = np.asarray(curve["wavelength_nm"], dtype=float)
            k = np.asarray(curve["k"], dtype=float)
            tail = k[(wl >= 1000) & (wl <= 1060)]
            self.assertTrue(np.isfinite(tail).all())
            self.assertLess(float(np.max(np.abs(np.diff(tail)))), 0.08)
            self.assertLess(float(np.max(tail)), 1.2)

    def test_thickness_sweep_api_returns_best(self):
        client = app.test_client()
        response = client.post(
            "/api/thickness/sweep",
            json={
                "template_id": "all_perovskite_planar_reference",
                "wavelength": {"start_nm": 300, "stop_nm": 360, "step_nm": 20},
                "thickness_scan": {
                    "layers": [
                        {"layer_name": "WBG active layer", "start_nm": 400, "stop_nm": 420, "step_nm": 20},
                        {"layer_name": "NBG active layer", "start_nm": 780, "stop_nm": 800, "step_nm": 20},
                    ]
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("best", response.json)
        self.assertEqual(len(response.json["scan_axes"]), 2)
        self.assertGreater(len(response.json["results"]), 1)


class RcwaGeometryTests(unittest.TestCase):
    def test_sawtooth_mask_dimensions(self):
        masks = generate_shape_masks("Sawtooth", 500, N_slices=4, Nx=8, Ny=6, duty_cycle=0.5)
        self.assertEqual(masks.shape, (4, 8, 6))
        self.assertGreater(masks.sum(), 0)


class ApiTests(unittest.TestCase):
    def test_materials_endpoint(self):
        client = app.test_client()
        response = client.get("/api/materials")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.json["materials"]), 5)
        templates = response.json["templates"]
        self.assertIn("All-perovskite tandem", [item["name"] for item in templates])
        self.assertNotIn("all_perovskite_legacy_tmm", [item["id"] for item in templates])

    def test_tmm_endpoint(self):
        client = app.test_client()
        response = client.post(
            "/api/simulate/tmm",
            json={"template_id": "all_perovskite", "wavelength": {"start_nm": 300, "stop_nm": 320, "step_nm": 20}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["method"], "tmm")
        self.assertEqual(response.json["geometry"], "planar")

    def test_tmm_endpoint_ignores_periodic_payload(self):
        client = app.test_client()
        base = {"template_id": "all_perovskite", "wavelength": {"start_nm": 300, "stop_nm": 340, "step_nm": 20}}
        periodic = {
            **base,
            "rcwa": {"periodic": True, "shape": "Sawtooth", "pitch": 500, "height": 500, "duty_cycle": 0.5, "nG": 18, "slices": 4},
        }
        base_response = client.post("/api/simulate/tmm", json=base)
        periodic_response = client.post("/api/simulate/tmm", json=periodic)
        self.assertEqual(periodic_response.status_code, 200)
        self.assertEqual(periodic_response.json["geometry"], "planar")
        self.assertEqual(periodic_response.json["reflection"], base_response.json["reflection"])

    def test_rcwa_metadata_and_ng_normalization(self):
        result = run_rcwa({"rcwa": {"periodic": False, "shape": "Planar", "nG": 18, "pitch": 500, "height": 500, "slices": 4}})
        self.assertEqual(result["method"], "rcwa")
        self.assertEqual(result["geometry"], "planar")
        self.assertEqual(result["periodic_parameters"]["nG"], 19)
        self.assertIn("model_note", result)

    def test_compare_type_tmm_flat_vs_rcwa_flat_starts_cleanly(self):
        client = app.test_client()
        response = client.post(
            "/api/simulate/compare",
            json={
                "compare_type": "tmm_flat_vs_rcwa_flat",
                "template_id": "all_perovskite",
                "wavelength": {"start_nm": 300, "stop_nm": 320, "step_nm": 20},
                "rcwa": {"periodic": True, "shape": "Sawtooth", "pitch": 500, "height": 500, "duty_cycle": 0.5, "nG": 17, "slices": 4},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["compare_type"], "tmm_flat_vs_rcwa_flat")
        self.assertEqual(response.json["tmm"]["geometry"], "planar")

    def test_csv_export_includes_model_metadata(self):
        csv_text = result_to_csv(
            {
                "method": "rcwa",
                "geometry": "periodic",
                "shape": "Sawtooth",
                "model_note": "RCWA supports periodic/textured structures.",
                "periodic_parameters": {"pitch": 500, "height": 400, "duty_cycle": 0.5, "nG": 17, "slices": 4},
                "wavelength_nm": [300, 320],
                "reflection": [0.1, 0.2],
                "layers": [],
            }
        )
        self.assertIn("# method,rcwa", csv_text)
        self.assertIn("# geometry,periodic", csv_text)
        self.assertIn("# periodic_pitch,500", csv_text)


if __name__ == "__main__":
    unittest.main()
