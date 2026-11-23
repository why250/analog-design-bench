"""Render the candidate evidence needed at the second review point."""


def _db(value):
    return f"{value:.3f}" if value is not None else "Unavailable"


def _metric_rows(candidate):
    metrics = candidate["metrics"]
    metrics_by_label = [
        ("Worst S11", metrics["s11_worst"]),
        ("Worst S22", metrics["s22_worst"]),
        ("Worst insertion loss", metrics["il_worst"]),
        *(("S21 checkpoint", item) for item in metrics["stopbands"]),
    ]
    for label, item in metrics_by_label:
        value, limit = item["value_db"], item["limit_db"]
        margin = limit - value if value is not None and limit is not None else None
        frequency = item["frequency_hz"]
        frequency_text = f"{frequency / 1e9:.8g}" if frequency is not None else "Unavailable"
        limit_text = "Report only" if limit is None else _db(limit)
        yield f"| {label} | {frequency_text} | {_db(value)} | {limit_text} | {_db(margin)} |"


def write_pcell_review(path, report):
    lines = ["# PCell candidate review", "", "Select the candidate to take into editable layout after review.", ""]
    counts = report.get("search_counts", {})
    if counts:
        lines.extend([
            f"Evaluated {counts.get('paired', 0)} paired and {counts.get('unpaired', 0)} "
            f"independent-size candidates. Attempted {counts.get('ads_runs', 0)} native reruns.", "",
        ])
    candidates = {item["id"]: item for item in report.get("candidates", [])}
    selected = [item for item in candidates.values() if item.get("verification") == "ads"]
    selected.sort(key=lambda item: (not item["passes"], item["metrics"]["il_worst"]["value_db"] is None,
                                    item["metrics"]["il_worst"]["value_db"] or 0.0, item["id"]))
    best = candidates.get(report.get("best_candidate_id"))
    near_miss = candidates.get(report.get("best_near_miss_id"))
    for item in (best, near_miss):
        if item and item not in selected:
            selected.append(item)
    if not selected:
        lines.extend(["No candidate has usable circuit evidence. Inspect the search results for model or simulation gaps.", ""])
    for item in selected:
        verification = "Native ADS" if item["verification"] == "ads" else "Model screening"
        result = "Sampled limits met" if item["passes"] else "Electrical limits missed"
        lines.extend([
            f"## {item['id']}", "", f"{verification}. {result}. Model status **{item['model_status']}**.", "",
            "| Metric | Frequency (GHz) | Measured (dB) | Limit (dB) | Margin (dB) |",
            "| --- | --- | --- | --- | --- |", *_metric_rows(item), "",
            "| Instance | Geometry (µm) |", "| --- | --- |",
        ])
        for device in item.get("devices", []):
            parameters = ", ".join(f"{name}={value:g}" for name, value in sorted(device["parameters"].items()))
            lines.append(f"| {device['name']} | {parameters} |")
        lines.append("")
        lines.extend(f"- {note}" for note in item.get("model_notes", []))
        lines.append("")
    if report.get("issues"):
        lines.extend([f"The search result records {len(report['issues'])} model, coverage or run issues.", ""])
    requests = report.get("extraction_requests", [])
    pending = sum(request.get("status") == "pending_ads" for request in requests)
    if pending:
        lines.extend([f"{pending} new geometries await exact ADS samples. See the extraction requests and receipts.", ""])
    lines.extend(f"- {note}" for note in report.get("recommendations", []))
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
