from __future__ import annotations

from flask import Flask, Response, jsonify, render_template, request

from optics_core.export import result_to_csv
from optics_core.jobs import JobManager
from optics_core.materials import MaterialDatabase, parse_numeric_table
from optics_core.rcwa_engine import run_rcwa
from optics_core.templates import list_templates
from optics_core.temperature import run_temperature_sweep
from optics_core.thickness import run_thickness_sweep
from optics_core.tmm_engine import run_tmm

app = Flask(__name__)
material_db = MaterialDatabase()
jobs = JobManager(max_workers=1)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/materials")
def api_materials():
    return jsonify({"materials": material_db.summaries(), "templates": list_templates()})


@app.post("/api/materials/validate")
def api_validate_material():
    file = request.files.get("file")
    text = file.read().decode("utf-8", errors="ignore") if file else request.get_data(as_text=True)
    wl, n, k = parse_numeric_table(text)
    return jsonify(
        {
            "valid": True,
            "points": int(len(wl)),
            "wavelength_min_nm": float(wl.min()),
            "wavelength_max_nm": float(wl.max()),
            "n_min": float(n.min()),
            "n_max": float(n.max()),
            "k_min": float(k.min()),
            "k_max": float(k.max()),
            "preview": [{"wavelength_nm": float(wl[i]), "n": float(n[i]), "k": float(k[i])} for i in range(min(8, len(wl)))],
        }
    )


@app.post("/api/simulate/tmm")
def api_tmm():
    result = run_tmm(_tmm_planar_payload(request.get_json(force=True)), material_db)
    return jsonify(result)


@app.post("/api/simulate/rcwa")
def api_rcwa():
    payload = request.get_json(force=True)
    job_id = jobs.submit(run_rcwa, payload)
    return jsonify({"job_id": job_id})


@app.get("/api/jobs/<job_id>")
def api_job(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.post("/api/simulate/compare")
def api_compare():
    payload = request.get_json(force=True)
    compare_type = str(payload.get("compare_type", "tmm_flat_vs_rcwa_flat"))
    if compare_type not in {"tmm_flat_vs_rcwa_flat", "rcwa_flat_vs_periodic"}:
        return jsonify({"error": "Invalid compare_type."}), 400

    if compare_type == "tmm_flat_vs_rcwa_flat":
        tmm_result = run_tmm(_tmm_planar_payload(payload), material_db)

        def compare_task(inner_payload, progress=None):
            if progress:
                progress(5, "TMM planar result already complete; running RCWA planar.")
            rcwa_result = run_rcwa(_rcwa_payload(inner_payload, periodic=False), progress=progress)
            return {"compare_type": compare_type, "tmm": tmm_result, "rcwa_flat": rcwa_result}

        job_id = jobs.submit(compare_task, payload)
        return jsonify({"job_id": job_id, "tmm": tmm_result, "compare_type": compare_type})

    def compare_task(inner_payload, progress=None):
        if progress:
            progress(5, "Running RCWA planar reference.")
        rcwa_flat = run_rcwa(_rcwa_payload(inner_payload, periodic=False), progress=progress)
        if progress:
            progress(55, "Running RCWA periodic structure.")
        rcwa_periodic = run_rcwa(_rcwa_payload(inner_payload, periodic=True), progress=progress)
        return {"compare_type": compare_type, "rcwa_flat": rcwa_flat, "rcwa_periodic": rcwa_periodic}

    job_id = jobs.submit(compare_task, payload)
    return jsonify({"job_id": job_id, "compare_type": compare_type})


@app.post("/api/temperature/sweep")
def api_temperature():
    result = run_temperature_sweep(request.get_json(force=True), material_db)
    return jsonify(result)


@app.post("/api/thickness/sweep")
def api_thickness():
    result = run_thickness_sweep(request.get_json(force=True), material_db)
    return jsonify(result)


@app.post("/api/export/csv")
def api_export_csv():
    result = request.get_json(force=True)
    csv_text = result_to_csv(result)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=optical_results.csv"},
    )


@app.errorhandler(Exception)
def handle_error(exc):
    return jsonify({"error": str(exc)}), 500


def _tmm_planar_payload(payload: dict) -> dict:
    cleaned = dict(payload)
    cleaned["rcwa"] = {}
    return cleaned


def _rcwa_payload(payload: dict, periodic: bool) -> dict:
    cleaned = dict(payload)
    rcwa = dict(cleaned.get("rcwa", {}))
    rcwa["periodic"] = periodic
    if not periodic:
        rcwa["shape"] = "Planar"
    elif str(rcwa.get("shape", "Planar")).lower() == "planar":
        rcwa["shape"] = "Paraboloid"
    cleaned["rcwa"] = rcwa
    return cleaned


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True, threaded=True)
