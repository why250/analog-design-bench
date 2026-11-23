"""Independent rational-network analysis for the synthetic Stage 2 RLC study.

The polynomial variable is p=s/(2*pi*65 GHz); magnitude polynomials use
x=(f/65 GHz)**2. Decimal Sturm sequences provide numerical root counts and
isolating intervals. A second precision and a separate dense scattering grid
check their conditioning. This module never creates ADS evidence.
"""

from __future__ import annotations

import csv
from decimal import Decimal, localcontext
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

try:
    from . import model
except ImportError:
    import model

FP = 65e9
W0 = 2 * math.pi * FP
Z0 = 50.0
METRICS = {"s11_worst": (0, 0, True, 0.1),
           "s22_worst": (1, 1, True, 0.1),
           "il_worst": (1, 0, False, 10 ** (-1 / 20))}
FIELDS = ["freq_hz", "s11_real", "s11_imag", "s21_real", "s21_imag",
          "s12_real", "s12_imag", "s22_real", "s22_imag"]


def _d(value):
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _trim(a, relative=None):
    a = list(a)
    if not a:
        return [Decimal(0)]
    scale = max(abs(v) for v in a)
    eps = scale * (relative if relative is not None else Decimal("1e-60"))
    while len(a) > 1 and abs(a[-1]) <= eps:
        a.pop()
    return a


def _add(a, b, sign=1):
    c = [Decimal(0)] * max(len(a), len(b))
    for i, v in enumerate(a):
        c[i] += v
    for i, v in enumerate(b):
        c[i] += sign * v
    return _trim(c)


def _mul(a, b):
    c = [Decimal(0)] * (len(a) + len(b) - 1)
    for i, v in enumerate(a):
        for j, w in enumerate(b):
            c[i + j] += v * w
    return _trim(c)


def _der(a):
    return [i * a[i] for i in range(1, len(a))] or [Decimal(0)]


def _val(a, x):
    result = Decimal(0)
    for v in reversed(a):
        result = result * x + v
    return result


def _norm(a):
    scale = max(abs(v) for v in a)
    return [v / scale for v in a] if scale else [Decimal(0)]


def _remainder(a, b, eps):
    remainder = list(a)
    for k in range(len(a) - len(b), -1, -1):
        coefficient = remainder[len(b) - 1 + k] / b[-1]
        for j in range(len(b)):
            remainder[j + k] -= coefficient * b[j]
        remainder[len(b) - 1 + k] = Decimal(0)
    return _trim(remainder[:max(1, len(b) - 1)], eps)


def _sturm(a, precision):
    eps = Decimal(10) ** (-precision + 20)
    a = _trim(a, eps)
    # Roots at DC are evaluated directly and do not belong to the open interval.
    zero_multiplicity = 0
    while len(a) > 1 and abs(a[0]) <= max(abs(v) for v in a) * eps:
        a = a[1:]
        zero_multiplicity += 1
    if len(a) == 1:
        return [_norm(a)], zero_multiplicity, 0
    sequence = [_norm(a), _norm(_der(a))]
    gcd_degree = 0
    while len(sequence[-1]) > 1:
        r = _remainder(sequence[-2], sequence[-1], eps)
        scale = max(abs(v) for v in r)
        if scale < eps:
            gcd_degree = len(sequence[-1]) - 1
            break
        sequence.append(_norm([-v for v in r]))
    return sequence, zero_multiplicity, gcd_degree


def _variations(sequence, x):
    signs = []
    for a in sequence:
        value = _val(a, x)
        if value:
            signs.append(value > 0)
    return sum(a != b for a, b in zip(signs[:-1], signs[1:]))


def _root_intervals(a, precision, max_frequency_width_hz=0.01):
    sequence, dc_mult, gcd_degree = _sturm(a, precision)
    left, right = Decimal(0), Decimal(1)
    count = _variations(sequence, left) - _variations(sequence, right)
    if count < 0 or count > len(a) - 1:
        raise ArithmeticError("Invalid Sturm root count")
    pending = [(left, right, count)]
    roots = []
    while pending:
        lo, hi, n = pending.pop()
        if n == 0:
            continue
        width_hz = (hi.sqrt() - lo.sqrt()) * _d(FP)
        if n == 1 and width_hz <= _d(max_frequency_width_hz):
            roots.append((lo, hi))
            continue
        mid = (lo + hi) / 2
        if mid == lo or mid == hi:
            raise ArithmeticError("Root interval failed to contract")
        vl, vm, vh = (_variations(sequence, x) for x in (lo, mid, hi))
        nleft, nright = vl - vm, vm - vh
        if nleft < 0 or nright < 0 or nleft + nright != n:
            raise ArithmeticError("Inconsistent Sturm subdivision count")
        pending.extend([(mid, hi, nright), (lo, mid, nleft)])
    roots.sort()
    return roots, {"root_count_open_dc_to_65g": count,
                   "isolated_root_count": len(roots),
                   "dc_stationary_multiplicity": dc_mult,
                   "stationary_gcd_degree": gcd_degree,
                   "sturm_sequence_degrees": [len(v) - 1 for v in sequence]}


def _magnitude_squared(a):
    even = [v * (-1) ** i for i, v in enumerate(a[::2])]
    odd = [v * (-1) ** i for i, v in enumerate(a[1::2])]
    result = _mul(even, even)
    if odd:
        result = _add(result, [Decimal(0)] + _mul(odd, odd))
    return _trim(result)


def _polynomials(manifest):
    """Return normalized ABCD-derived S numerators and common denominator."""
    one, zero = [Decimal(1)], [Decimal(0)]
    a, b, c, d = one, zero, zero, one
    h = one
    for e in manifest["elements"]:
        value = _d(e["value_si"])
        if e["kind"] == "L":
            rs, cp = _d(e.get("rs_ohm", 0)), _d(e.get("cp_f", 0))
            n = [rs / _d(Z0), _d(W0) * value / _d(Z0)]
            q = _trim([Decimal(1), _d(W0) * cp * rs,
                       _d(W0) ** 2 * cp * value])
            a, b, c, d = (_mul(a, q), _add(_mul(a, n), _mul(b, q)),
                          _mul(c, q), _add(_mul(c, n), _mul(d, q)))
        else:
            esr, esl = _d(e.get("esr_ohm", 0)), _d(e.get("esl_h", 0))
            n = [Decimal(0), _d(Z0) * _d(W0) * value]
            q = _trim([Decimal(1), _d(W0) * value * esr,
                       _d(W0) ** 2 * value * esl])
            a, b, c, d = (_add(_mul(a, q), _mul(b, n)), _mul(b, q),
                          _add(_mul(c, q), _mul(d, n)), _mul(d, q))
        h = _mul(h, q)
    denominator = _add(_add(a, b), _add(c, d))
    n11 = _add(_add(a, b), _add(c, d), -1)
    n22 = _add(_add(b, d), _add(a, c), -1)
    n21 = [2 * v for v in h]
    return {"s11_worst": n11, "s22_worst": n22, "il_worst": n21}, denominator


def rational_polynomials(manifest, precision=80):
    """JSON-safe coefficients, ascending powers of normalized p=s/W0."""
    model.validate(manifest)
    with localcontext() as ctx:
        ctx.prec = precision
        numerators, denominator = _polynomials(manifest)
        return {"variable": "p=s/(2*pi*65e9)", "coefficient_order": "ascending",
                "numerators": {k: [str(v) for v in a] for k, a in numerators.items()},
                "denominator": [str(v) for v in denominator],
                "precision_digits": precision}


def _ival(a, lo, hi):
    """Interval Horner enclosure; arithmetic rounding is padded separately."""
    low, high = Decimal(0), Decimal(0)
    for v in reversed(a):
        products = [low * lo, low * hi, high * lo, high * hi]
        low, high = min(products) + v, max(products) + v
    return low, high


def _mag_interval(u, v, lo, hi):
    ul, uh = _ival(u, lo, hi)
    vl, vh = _ival(v, lo, hi)
    if vl <= 0:
        raise ArithmeticError("Magnitude denominator enclosure includes zero")
    padding = Decimal("1e-45") * max(Decimal(1), abs(ul), abs(uh), abs(vl), abs(vh))
    lower = max(Decimal(0), (ul - padding) / (vh + padding))
    upper = max(Decimal(0), (uh + padding) / (vl - padding))
    return float(lower.sqrt()), float(upper.sqrt())


def _stationary_analysis(manifest, precision):
    with localcontext() as ctx:
        ctx.prec = precision
        numerators, denominator = _polynomials(manifest)
        v = _magnitude_squared(denominator)
        _, den_count = _root_intervals(v, precision)
        if den_count["root_count_open_dc_to_65g"]:
            raise ArithmeticError("Network magnitude denominator has a passband zero")
        metrics = {}
        for name, numerator in numerators.items():
            u = _magnitude_squared(numerator)
            g = _add(_mul(_der(u), v), _mul(u, _der(v)), -1)
            roots, diagnostic = _root_intervals(g, precision)
            candidates = [(Decimal(0), Decimal(0))] + roots + [(Decimal(1), Decimal(1))]
            extrema = []
            for lo, hi in candidates:
                midpoint = (lo + hi) / 2
                mag_bounds = _mag_interval(u, v, lo, hi)
                scale = _val([abs(w) for w in g], abs(midpoint))
                residual = abs(_val(g, midpoint)) / max(scale, Decimal("1e-60"))
                deriv = abs(_val(_der(g), midpoint))
                conditioning = scale / deriv if deriv else None
                curvature_sign = _val(_der(g), midpoint)
                extrema.append({"frequency_hz": float(midpoint.sqrt() * _d(FP)),
                                "frequency_interval_hz": [float(lo.sqrt() * _d(FP)), float(hi.sqrt() * _d(FP))],
                                "x_interval_decimal": [str(lo), str(hi)],
                                "magnitude_interval": list(mag_bounds),
                                "stationary_scaled_residual": float(residual),
                                "root_condition_scale_over_derivative": float(conditioning) if conditioning is not None else None,
                                "type": "endpoint" if lo == hi else "maximum" if curvature_sign < 0 else "minimum" if curvature_sign > 0 else "flat",
                                "endpoint": lo == hi})
            metrics[name] = {**diagnostic, "stationary_degree": len(g) - 1,
                             "extrema": extrema,
                             "magnitude_squared_numerator": [str(w) for w in u],
                             "magnitude_squared_denominator": [str(w) for w in v]}
        return metrics


def _dense_grid_check(manifest, metrics):
    # A deliberately independent linear-f grid, including the unsimulated low band.
    f = np.unique(np.r_[np.linspace(0, FP, 32769), np.geomspace(1e-3, 1e6, 257)])
    s = model.abcd_s(f, manifest)
    results = {}
    for name, (outp, inp, maximize, _) in METRICS.items():
        y = np.abs(s[:, outp, inp])
        delta = np.diff(y)
        indices = np.flatnonzero((delta[:-1] * delta[1:] < 0)) + 1
        roots = [e["frequency_hz"] for e in metrics[name]["extrema"] if not e["endpoint"]]
        unmatched = []
        max_step = float(np.max(np.diff(f)))
        for index in indices:
            if not roots or min(abs(f[index] - r) for r in roots) > 2 * max_step:
                # Machine roundoff in an essentially constant low-frequency response
                # does not constitute a physically resolved stationary point.
                prominence = abs(y[index] - (y[index - 1] + y[index + 1]) / 2)
                if prominence > 1e-12:
                    unmatched.append(float(f[index]))
        predicted_extreme = (max if maximize else min)(
            (max(e["magnitude_interval"]) if maximize else min(e["magnitude_interval"]))
            for e in metrics[name]["extrema"])
        sampled_extreme = float(np.max(y) if maximize else np.min(y))
        enclosed = sampled_extreme <= predicted_extreme + 1e-9 if maximize else sampled_extreme >= predicted_extreme - 1e-9
        results[name] = {"grid_points": len(f), "maximum_frequency_step_hz": max_step,
                         "discovered_stationary_neighborhoods": [float(f[i]) for i in indices if f[i] >= 1e6],
                         "unmatched_resolved_extrema_hz": unmatched,
                         "sampled_extreme_magnitude": sampled_extreme,
                         "rational_encloses_dense_extreme": bool(enclosed),
                         "ok": bool(not unmatched and enclosed)}
    return results


def predict(manifest, precision=80, check_precision=110):
    """Return actual-model extrema, brackets and proposed ADS sample locations.

    The separate precision repeats root counts and isolation. The resulting
    bounds are numerical enclosures for the declared double-precision physical
    coefficients, not a statement about real component model accuracy.
    """
    model.validate(manifest)
    primary = _stationary_analysis(manifest, precision)
    secondary = _stationary_analysis(manifest, check_precision)
    comparisons = {}
    for name in METRICS:
        p = primary[name]
        q = secondary[name]
        pf = np.array([e["frequency_hz"] for e in p["extrema"]])
        qf = np.array([e["frequency_hz"] for e in q["extrema"]])
        error = float(np.max(np.abs(pf - qf))) if pf.shape == qf.shape else None
        comparisons[name] = {"counts_agree": p["root_count_open_dc_to_65g"] == q["root_count_open_dc_to_65g"],
                             "maximum_frequency_difference_hz": error,
                             "ok": bool(error is not None and error <= 1)}
    dense = _dense_grid_check(manifest, primary)
    frequency_list = sorted(set(e["frequency_hz"] for m in primary.values() for e in m["extrema"]))
    # DC is an analytical limit, never an ADS zero-frequency SP request.
    positive_extrema = [f for f in frequency_list if 1e6 <= f <= FP]
    low_band = {}
    for name in METRICS:
        low_roots = [e for e in primary[name]["extrema"] if 0 < e["frequency_hz"] < 1e6]
        with localcontext() as ctx:
            ctx.prec = precision
            u = [_d(v) for v in primary[name]["magnitude_squared_numerator"]]
            v = [_d(w) for w in primary[name]["magnitude_squared_denominator"]]
            interval = _mag_interval(u, v, Decimal(0), (_d(1e6) / _d(FP)) ** 2)
        low_band[name] = {"band_hz": [0, 1e6], "stationary_root_count": len(low_roots),
                          "magnitude_interval": list(interval), "method": "interval Horner rational enclosure"}
    ok = all(v["ok"] for v in comparisons.values()) and all(v["ok"] for v in dense.values())
    residual_ok = all(e["stationary_scaled_residual"] <= 1e-8
                      for m in primary.values() for e in m["extrema"] if not e["endpoint"])
    ok = ok and residual_ok
    return {"method": "scaled polynomial ABCD; Decimal Sturm isolation; dual precision; independent scattering grid",
            "physical_sha256": model.physical_hash(manifest),
            "precision_digits": [precision, check_precision], "root_interval_width_target_hz": 0.01,
            "metrics": primary, "dual_precision": comparisons, "dense_check": dense,
            "extrema_hz": positive_extrema, "all_extrema_hz": frequency_list,
            "low_frequency_bounds": low_band, "coverage_justified": bool(ok),
            "stationary_residuals_ok": bool(residual_ok),
            "numerical_scope": "Numerical isolation of the declared finite-coefficient rational model; no physical-model error bound"}


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            raise ValueError("Unexpected complex-S CSV header")
        data = np.array([[float(row[k]) for k in FIELDS] for row in reader])
    if data.ndim != 2 or data.shape[1] != 9 or not len(data) or not np.isfinite(data).all():
        raise ValueError("Missing or nonfinite complex-S CSV data")
    s = np.empty((len(data), 2, 2), complex)
    for j, outp, inp in [(1, 0, 0), (3, 1, 0), (5, 0, 1), (7, 1, 1)]:
        s[:, outp, inp] = data[:, j] + 1j * data[:, j + 1]
    order = np.argsort(data[:, 0], kind="stable")
    f, s = data[order, 0], s[order]
    uf, indices, counts = np.unique(f, return_index=True, return_counts=True)
    for index, count in zip(indices, counts):
        if count > 1 and np.max(np.abs(s[index:index + count] - s[index])) > 1e-8:
            raise ValueError("Conflicting duplicate complex-S exports")
    return uf, s[indices]


def _db(magnitude, insertion=False):
    if magnitude == 0:
        return None, "positive_infinity" if insertion else "negative_infinity"
    return float((-20 if insertion else 20) * math.log10(magnitude)), "finite"


def _metric_record(name, magnitude, frequency, uncertainty, lower, upper,
                   continuous, tied_extrema):
    insertion = name == "il_worst"
    value_db, db_status = _db(magnitude, insertion)
    limit = METRICS[name][3]
    if name == "il_worst":
        state = "PASS" if continuous and lower > limit else "FAIL" if upper <= limit else "INDETERMINATE"
        signed_margin = magnitude - limit
        margin_db = 1 - value_db if value_db is not None else None
        relation = ">"
    else:
        state = "PASS" if continuous and upper < limit else "FAIL" if lower >= limit else "INDETERMINATE"
        signed_margin = limit - magnitude
        margin_db = -20 - value_db if value_db is not None else None
        relation = "<"
    return {"value_db": value_db, "db_status": db_status, "magnitude": float(magnitude),
            "frequency_hz": float(frequency), "magnitude_interval": [float(lower), float(upper)],
            "uncertainty_magnitude": float(uncertainty), "signed_margin_magnitude": float(signed_margin),
            "signed_margin_db": margin_db, "comparison_magnitude": relation,
            "limit_magnitude": limit, "state": state, "tied_extrema": tied_extrema,
            "reported_tie_resolution_db": 0.005}


def measured_round(freq_hz, s, prediction, maximum_spacing_hz):
    """Summarize one declared ADS subgrid, preserving every tracked extremum.

    A stable earliest representative is used for tied worst peaks. A trace's
    zero/minimum uses magnitude convergence below 1e-12 to avoid meaningless
    dB comparisons at a reflection zero.
    """
    f, s = np.asarray(freq_hz, float), np.asarray(s, complex)
    mask = f <= FP + 1
    pf, ps = f[mask], s[mask]
    metrics, tracked = {}, {}
    for name, (outp, inp, maximize, _) in METRICS.items():
        y = np.abs(ps[:, outp, inp])
        worst = float(np.max(y) if maximize else np.min(y))
        db, ds = _db(worst, name == "il_worst")
        tolerance = max(1e-13, worst * (10 ** (0.005 / 20) - 1))
        ties = np.flatnonzero(abs(y - worst) <= tolerance)
        metrics[name] = {"value_db": db, "db_status": ds, "magnitude": worst,
                         "frequency_hz": float(pf[int(ties[0])]),
                         "tie_frequency_hz": [float(pf[int(i)]) for i in ties]}
        tracked[name] = []
        for e in prediction["metrics"][name]["extrema"]:
            if e["frequency_hz"] < 1e6:
                continue
            near = np.flatnonzero(abs(pf - e["frequency_hz"]) <= 400e3 + 1)
            if not len(near):
                raise ValueError("Declared subgrid omits a tracked extremum")
            local_y = y[near]
            maximum = e["type"] == "maximum"
            minimum = e["type"] == "minimum"
            if maximum or minimum:
                local_worst = float(np.max(local_y) if maximum else np.min(local_y))
                # A fixed root-centered tie representative avoids selecting
                # arbitrary sides of a flat peak on successive subgrids.
                local_tol = max(1e-14, local_worst * 1e-12)
                tied = near[abs(local_y - local_worst) <= local_tol]
                i = int(tied[np.argmin(abs(pf[tied] - e["frequency_hz"]))])
            else:
                i = int(near[np.argmin(abs(pf[near] - e["frequency_hz"]))])
            magnitude = float(y[i])
            local_db, local_ds = _db(magnitude)
            tracked[name].append({"target_hz": e["frequency_hz"], "frequency_hz": float(pf[i]),
                                  "magnitude": magnitude, "value_db": local_db,
                                  "db_status": local_ds, "type": e["type"]})
    return {"maximum_spacing_hz": float(maximum_spacing_hz), "metrics": metrics,
            "tracked_extrema": tracked}


def _refinement_status(history):
    """Validate two successive measured local refinement comparisons.

    Each entry must provide metrics[name] with value_db, frequency_hz and
    optional magnitude, plus maximum_spacing_hz. Callers retain source CSVs
    and settings; histories only summarize observations from those files.
    """
    if not history or len(history) < 3:
        return {"ok": False, "reason": "Three measured rounds required for two successive convergence comparisons"}
    comparisons = []
    for before, after in zip(history[-3:-1], history[-2:]):
        deltas, tracked_checks = {}, {}
        for name in METRICS:
            a, b = before.get("metrics", {}).get(name, {}), after.get("metrics", {}).get(name, {})
            if a.get("value_db") is not None and b.get("value_db") is not None:
                delta = abs(b["value_db"] - a["value_db"])
                value_ok = delta <= 0.005
            else:
                delta = abs(b.get("magnitude", math.inf) - a.get("magnitude", -math.inf))
                value_ok = math.isfinite(delta) and delta <= 1e-9
            freqdelta = abs(b.get("frequency_hz", math.inf) - a.get("frequency_hz", -math.inf))
            deltas[name] = {"value_change_db_or_magnitude": delta if math.isfinite(delta) else None,
                            "frequency_change_hz": freqdelta if math.isfinite(freqdelta) else None,
                            "ok": bool(value_ok and freqdelta <= 1e6)}
            ta = before.get("tracked_extrema", {}).get(name, [])
            tb = after.get("tracked_extrema", {}).get(name, [])
            checks = []
            for aroot, broot in zip(ta, tb):
                same_target = abs(aroot["target_hz"] - broot["target_hz"]) <= 1
                if min(aroot["magnitude"], broot["magnitude"]) <= 1e-12:
                    value_ok = abs(aroot["magnitude"] - broot["magnitude"]) <= 1e-9
                else:
                    value_ok = abs(aroot["value_db"] - broot["value_db"]) <= .005
                frequency_ok = abs(aroot["frequency_hz"] - broot["frequency_hz"]) <= 1e6
                checks.append(bool(same_target and value_ok and frequency_ok))
            tracked_checks[name] = {"tracked_count_before": len(ta), "tracked_count_after": len(tb),
                                     "ok": bool(len(ta) == len(tb) and len(ta) > 0 and all(checks))}
        spacing_ok = (after.get("maximum_spacing_hz", math.inf) <= before.get("maximum_spacing_hz", 0) / 2 + 1)
        comparisons.append({"metrics": deltas, "tracked_extrema": tracked_checks,
                            "spacing_halved": bool(spacing_ok),
                            "ok": bool(spacing_ok and all(x["ok"] for x in deltas.values()) and all(x["ok"] for x in tracked_checks.values()))})
    return {"ok": all(x["ok"] for x in comparisons), "comparisons": comparisons,
            "rounds": len(history)}


def verify(freq_hz, s, manifest, prediction=None, refinement_history=None):
    """Measure ADS data and retain conservative continuous-band result states."""
    try:
        model.validate(manifest)
        f = np.asarray(freq_hz, float)
        s = np.asarray(s, complex)
        if f.ndim != 1 or len(f) < 2 or s.shape != (len(f), 2, 2):
            raise ValueError("Expected S[n,2,2] with at least two frequencies")
        if not np.isfinite(f).all() or not np.isfinite(s).all() or np.any(f <= 0) or np.any(np.diff(f) <= 0):
            raise ValueError("Frequency/S arrays must be finite, unique, sorted and positive")
    except (ValueError, TypeError, KeyError) as exc:
        return {"state": "INVALID", "reason": str(exc)}
    independent = model.abcd_s(f, manifest)
    error = float(np.max(np.abs(independent - s)))
    reciprocity = float(np.max(np.abs(s[:, 1, 0] - s[:, 0, 1])))
    identity = np.eye(2)[None, :, :]
    passive_matrices = identity - np.swapaxes(s.conj(), 1, 2) @ s
    min_eigenvalue = float(np.min(np.linalg.eigvalsh(passive_matrices)))
    ideal = all(not e.get(k, 0) for e in manifest["elements"] for k in ("rs_ohm", "cp_f", "esr_ohm", "esl_h"))
    unitary = float(np.max(np.abs(passive_matrices)))
    physics = {"complex_error_max": error, "reciprocity_error_max": reciprocity,
               "passivity_min_eigenvalue": min_eigenvalue, "ideal_recovery": ideal,
               "unitarity_residual": unitary if ideal else None,
               "ok": bool(error <= 1e-6 and reciprocity <= 1e-8 and min_eigenvalue >= -1e-8 and (not ideal or unitary <= 1e-8))}
    if not physics["ok"]:
        return {"state": "INVALID", "reason": "Independent circuit or physical check failed", "physics": physics}
    exact65 = np.flatnonzero(abs(f - FP) <= 1)
    exact80 = np.flatnonzero(abs(f - 80e9) <= 1)
    pb = f <= FP + 1
    pf = f[pb]
    maxgap = float(np.max(np.diff(pf))) if len(pf) > 1 else None
    required_grids = {}
    for label, required in [("broad", np.linspace(1e6, 120e9, 2401)),
                            ("passband", np.linspace(1e6, FP, 1301))]:
        index = np.searchsorted(f, required)
        high = f[np.clip(index, 0, len(f) - 1)]
        low = f[np.clip(index - 1, 0, len(f) - 1)]
        gaps = np.minimum(abs(high - required), abs(low - required))
        required_grids[label] = {"required_count": len(required),
                                  "missing_count": int(np.sum(gaps > 1)),
                                  "max_nearest_frequency_error_hz": float(np.max(gaps)),
                                  "ok": bool(np.max(gaps) <= 1)}
    basic = bool(len(exact65) and len(exact80) and f[0] <= 1e6 + 1 and f[-1] >= 120e9 - 1 and maxgap is not None and maxgap <= 50e6 + 1 and all(g["ok"] for g in required_grids.values()))
    pred = prediction if prediction is not None else predict(manifest)
    if pred.get("physical_sha256") != model.physical_hash(manifest):
        return {"state": "INVALID", "reason": "Extrema prediction belongs to a different resolved physical manifest", "physics": physics}
    coverage_extrema = []
    for target in pred["extrema_hz"]:
        index = int(np.argmin(abs(f - target)))
        endpoint = abs(target - FP) <= 1
        below = bool(np.any((f < target - 1) & (f >= max(1e6, target - 1e6) - 1)))
        above = bool(np.any((f > target + 1) & (f <= min(FP, target + 1e6) + 1)))
        coverage_extrema.append({"frequency_hz": target, "nearest_sample_hz": float(f[index]),
                                 "exact_sample": bool(abs(f[index] - target) <= 1),
                                 "bracket_below": below, "bracket_above": above,
                                 "ok": bool(abs(f[index] - target) <= 1 and (below or target <= 1e6 + 1) and (above or endpoint))})
    refinements = _refinement_status(refinement_history)
    tracked_complete = True
    if refinement_history:
        for observation in refinement_history:
            for name in METRICS:
                expected = [e["frequency_hz"] for e in pred["metrics"][name]["extrema"] if e["frequency_hz"] >= 1e6]
                actual = [e["target_hz"] for e in observation.get("tracked_extrema", {}).get(name, [])]
                tracked_complete = tracked_complete and len(expected) == len(actual) and all(abs(a-b) <= 1 for a, b in zip(expected, actual))
    refinements["all_predicted_extrema_tracked"] = bool(tracked_complete)
    refinements["ok"] = bool(refinements["ok"] and tracked_complete)
    # Discover resolved extrema directly from ADS observations, independent of roots.
    discovered = {}
    missed = []
    for name, (outp, inp, _, _) in METRICS.items():
        y = np.abs(s[pb, outp, inp])
        delta = np.diff(y)
        ids = np.flatnonzero(delta[:-1] * delta[1:] < 0) + 1
        roots = [e["frequency_hz"] for e in pred["metrics"][name]["extrema"]]
        discovered[name] = []
        for i in ids:
            prominence = abs(y[i] - (y[i - 1] + y[i + 1]) / 2)
            if prominence < 1e-12:
                continue
            found = min(abs(pf[i] - r) for r in roots) <= max(2 * (pf[i + 1] - pf[i - 1]), 1e6)
            discovered[name].append({"frequency_hz": float(pf[i]), "matched_rational_extremum": bool(found)})
            if not found:
                missed.append({"metric": name, "frequency_hz": float(pf[i])})
    continuous = bool(basic and pred["coverage_justified"] and all(v["ok"] for v in coverage_extrema) and refinements["ok"] and not missed)
    coverage = {"basic_grids_and_checkpoints": basic, "max_passband_gap_hz": maxgap,
                "required_grid_membership": required_grids,
                "exact_65ghz": bool(len(exact65)), "exact_80ghz": bool(len(exact80)),
                "extrema_samples": coverage_extrema, "rational_coverage": pred["coverage_justified"],
                "ads_grid_extrema": discovered, "unmatched_ads_extrema": missed,
                "local_refinement": refinements, "continuous_band_justified": continuous}
    # The error used in acceptance is actual ADS/circuit disagreement, with a
    # floating arithmetic floor; 1e-6 is a rejection limit, not uncertainty.
    uncertainty_floor = max(2 * error, 2e-12)
    dc = np.asarray(model.dc_s(manifest), complex)
    measured_f = np.r_[0.0, pf]
    measured_s = np.concatenate((dc[None, :, :], s[pb]), axis=0)
    metrics = {}
    for name, (outp, inp, maximize, _) in METRICS.items():
        y = np.abs(measured_s[:, outp, inp])
        index = int(np.argmax(y) if maximize else np.argmin(y))
        magnitude = float(y[index])
        local_refinement_uncertainty = 0.0
        if refinement_history and len(refinement_history) >= 2:
            for before, after in zip(refinement_history[-3:-1], refinement_history[-2:]):
                am = before.get("metrics", {}).get(name, {}).get("magnitude")
                bm = after.get("metrics", {}).get(name, {}).get("magnitude")
                if am is not None and bm is not None:
                    local_refinement_uncertainty = max(local_refinement_uncertainty, abs(am - bm))
                for aroot, broot in zip(before.get("tracked_extrema", {}).get(name, []),
                                        after.get("tracked_extrema", {}).get(name, [])):
                    local_refinement_uncertainty = max(local_refinement_uncertainty,
                                                      abs(aroot["magnitude"] - broot["magnitude"]))
        metric_uncertainty = uncertainty_floor + 2 * local_refinement_uncertainty
        ext = pred["metrics"][name]["extrema"]
        lower_global = (max(e["magnitude_interval"][0] for e in ext) if maximize
                        else min(e["magnitude_interval"][0] for e in ext))
        upper_global = (max(e["magnitude_interval"][1] for e in ext) if maximize
                        else min(e["magnitude_interval"][1] for e in ext))
        # Valid violating samples establish FAIL even if continuous coverage is
        # incomplete. Passing samples alone cannot establish continuous PASS.
        if maximize:
            lower = max(lower_global if continuous else 0, magnitude) - metric_uncertainty
            upper = max(upper_global, magnitude) + metric_uncertainty
        else:
            lower = min(lower_global, magnitude) - metric_uncertainty
            upper = min(upper_global if continuous else magnitude, magnitude) + metric_uncertainty
        lower = max(0.0, lower)
        uncertainty = max(abs(magnitude - lower), abs(upper - magnitude))
        threshold = 0.005 * math.log(10) / 20 * max(magnitude, 1e-20)
        tied = [{"frequency_hz": e["frequency_hz"], "magnitude_interval": e["magnitude_interval"]}
                for e in ext if abs(sum(e["magnitude_interval"]) / 2 - magnitude) <= threshold + uncertainty]
        metrics[name] = _metric_record(name, magnitude, measured_f[index], uncertainty,
                                       lower, upper, continuous, tied)
        metrics[name]["uncertainty_sources"] = {
            "ads_crosscheck_and_arithmetic_floor": uncertainty_floor,
            "twice_observed_local_refinement_change": 2 * local_refinement_uncertainty,
            "rational_extremum_enclosure": [lower_global, upper_global]}
    if len(exact80):
        j = int(exact80[0])
        magnitude = float(abs(s[j, 1, 0]))
        lower, upper = max(0, magnitude - uncertainty_floor), magnitude + uncertainty_floor
        state = "PASS" if upper <= 0.1 else "FAIL" if lower > 0.1 else "INDETERMINATE"
        db, ds = _db(magnitude)
        metrics["s21_80"] = {"value_db": db, "db_status": ds, "magnitude": magnitude,
                              "frequency_hz": float(f[j]), "magnitude_interval": [lower, upper],
                              "uncertainty_magnitude": uncertainty_floor,
                              "signed_margin_magnitude": 0.1 - magnitude,
                              "signed_margin_db": -20 - db if db is not None else None,
                              "comparison_magnitude": "<=", "limit_magnitude": 0.1, "state": state}
    else:
        metrics["s21_80"] = {"state": "INDETERMINATE", "reason": "Missing exact 80 GHz sample"}
    states = [m["state"] for m in metrics.values()]
    state = "FAIL" if "FAIL" in states else "PASS" if all(x == "PASS" for x in states) else "INDETERMINATE"
    checkpoints = {}
    if len(exact65):
        for name, (outp, inp, _, _) in METRICS.items():
            value = float(abs(s[int(exact65[0]), outp, inp]))
            db, ds = _db(value, name == "il_worst")
            checkpoints[name] = {"magnitude": value, "value_db": db, "db_status": ds}
    dc_metrics = {}
    for name, (outp, inp, _, _) in METRICS.items():
        magnitude = float(abs(dc[outp, inp]))
        db, ds = _db(magnitude, name == "il_worst")
        dc_metrics[name] = {"magnitude": magnitude, "value_db": db, "db_status": ds}
    return {"state": state, "metrics": metrics, "physics": physics, "coverage": coverage,
            "checkpoints_65ghz": checkpoints, "dc_limit": dc_metrics,
            "absorption_ranges": {"a1": [float(np.min(1 - abs(s[:, 0, 0])**2 - abs(s[:, 1, 0])**2)), float(np.max(1 - abs(s[:, 0, 0])**2 - abs(s[:, 1, 0])**2))],
                                  "a2": [float(np.min(1 - abs(s[:, 1, 1])**2 - abs(s[:, 0, 1])**2)), float(np.max(1 - abs(s[:, 1, 1])**2 - abs(s[:, 0, 1])**2))]},
            "model_scope": "Synthetic fixed-coefficient RLC; conditional electrical result only"}


def export_touchstone(path, f, s):
    with Path(path).open("w", encoding="ascii", newline="\n") as stream:
        stream.write("! Synthetic Stage 2; ports rfin/rfout, common gnd\n# Hz S RI R 50\n")
        for frequency, matrix in zip(f, s):
            values = [frequency]
            for outp, inp in [(0, 0), (1, 0), (0, 1), (1, 1)]:
                values.extend([matrix[outp, inp].real, matrix[outp, inp].imag])
            stream.write(" ".join(f"{v:.17g}" for v in values) + "\n")


def poles(manifest):
    """Resolve actual denominator poles, including tightly clustered real poles.

    Real poles are counted/isolated by Decimal Sturm sequences before deflation.
    Remaining complex roots use simultaneous Aberth refinement. Independent
    Newton polishing, coefficient reconstruction and disjoint Rouche disks
    reject a root list that merely repeats a small-residual root. None of these
    operations changes the circuit coefficients or electrical comparisons.
    """
    specification = rational_polynomials(manifest, precision=110)
    zero = (Decimal(0), Decimal(0))
    one = (Decimal(1), Decimal(0))

    def cadd(a, b):
        return a[0] + b[0], a[1] + b[1]

    def csub(a, b):
        return a[0] - b[0], a[1] - b[1]

    def cmul(a, b):
        return a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0]

    def cdiv(a, b):
        denominator = b[0] ** 2 + b[1] ** 2
        if not denominator:
            raise ArithmeticError("Coincident complex roots or zero Newton derivative")
        return ((a[0] * b[0] + a[1] * b[1]) / denominator,
                (a[1] * b[0] - a[0] * b[1]) / denominator)

    def cabs(z):
        return (z[0] ** 2 + z[1] ** 2).sqrt()

    def ceval(c, z):
        y = zero
        for coefficient in reversed(c):
            yr, yi = cmul(y, z)
            y = yr + coefficient, yi
        return y

    with localcontext() as ctx:
        ctx.prec = 160
        c = [_d(v) for v in specification["denominator"]]
        n = [_d(v) for v in specification["numerators"]["il_worst"]]
        degree = len(c) - 1
        sequence, dc_mult, gcd_degree = _sturm(c, ctx.prec)
        # Cauchy's bound encloses every real/complex root. Only logarithmically
        # many subdivisions depend on its conservative size.
        bound = Decimal(1) + max(abs(v / c[-1]) for v in c[:-1])
        real_count = _variations(sequence, -bound) - _variations(sequence, bound)
        pending = [(-bound, bound, real_count)]
        real_intervals = []
        while pending:
            lo, hi, count = pending.pop()
            if not count:
                continue
            midpoint = (lo + hi) / 2
            if count == 1 and hi - lo <= Decimal("1e-90") * max(Decimal(1), abs(midpoint)):
                real_intervals.append((lo, hi))
                continue
            if midpoint == lo or midpoint == hi:
                raise ArithmeticError("Real-pole Sturm interval stopped contracting")
            vl, vm, vh = (_variations(sequence, v) for v in (lo, midpoint, hi))
            left, right = vl - vm, vm - vh
            if min(left, right) < 0 or left + right != count:
                raise ArithmeticError("Inconsistent real-pole isolation count")
            pending.extend([(lo, midpoint, left), (midpoint, hi, right)])
        real_intervals.sort()
        real_roots = [((lo + hi) / 2, Decimal(0)) for lo, hi in real_intervals]
        derivative = _der(c)
        for index, root in enumerate(real_roots):
            for _ in range(40):
                correction = cdiv(ceval(c, root), ceval(derivative, root))
                root = csub(root, correction)
                if cabs(correction) <= Decimal("1e-135") * max(Decimal(1), cabs(root)):
                    break
            real_roots[index] = root
        # Remove resolved real roots first. An ill-conditioned full companion
        # matrix can turn a pair of nearby real poles into two misleading
        # conjugate seeds that both converge to the same root.
        reduced = list(c)
        deflation_residuals = []
        for root, _ in real_roots:
            quotient = [Decimal(0)] * (len(reduced) - 1)
            quotient[-1] = reduced[-1]
            for j in range(len(quotient) - 2, -1, -1):
                quotient[j] = reduced[j + 1] + root * quotient[j + 1]
            remainder = reduced[0] + root * quotient[0]
            scale = _val([abs(v) for v in reduced], abs(root))
            deflation_residuals.append(float(abs(remainder) / max(scale, Decimal("1e-150"))))
            reduced = quotient
        remaining_degree = len(reduced) - 1
        complex_roots = []
        iterations = 0
        if remaining_degree:
            initial = np.polynomial.polynomial.polyroots(np.array([float(v) for v in _norm(reduced)]))
            complex_roots = [(_d(float(v.real)), _d(float(v.imag))) for v in initial]
            if len(complex_roots) != remaining_degree:
                raise ArithmeticError("Reduced companion root count differs from degree")
            derivative = _der(reduced)
            for iterations in range(1, 241):
                updated, maximum_correction = [], Decimal(0)
                for i, z in enumerate(complex_roots):
                    newton = cdiv(ceval(reduced, z), ceval(derivative, z))
                    interaction = zero
                    for j, other in enumerate(complex_roots):
                        if i != j:
                            interaction = cadd(interaction, cdiv(one, csub(z, other)))
                    correction = cdiv(newton, csub(one, cmul(newton, interaction)))
                    updated.append(csub(z, correction))
                    maximum_correction = max(maximum_correction, cabs(correction) / max(Decimal(1), cabs(z)))
                complex_roots = updated
                if maximum_correction <= Decimal("1e-105"):
                    break
            else:
                raise ArithmeticError("Simultaneous complex-pole refinement did not converge")
        derivative = _der(c)
        roots = []
        for root in real_roots + complex_roots:
            for _ in range(50):
                correction = cdiv(ceval(c, root), ceval(derivative, root))
                root = csub(root, correction)
                if cabs(correction) <= Decimal("1e-110") * max(Decimal(1), cabs(root)):
                    break
            roots.append(root)
        roots.sort(key=lambda z: (z[0], z[1]))
        # Each disk contains exactly one zero when its linear Taylor term
        # dominates the constant + higher terms on its boundary (Rouche).
        # Arithmetic padding is far above 160-digit working roundoff.
        disks = []
        for root in roots:
            radius = Decimal("1e-70") * max(Decimal(1), cabs(root))
            scale = _val([abs(v) for v in c], cabs(root) + radius)
            constant = cabs(ceval(c, root)) + scale * Decimal("1e-140")
            slope = cabs(ceval(derivative, root))
            higher, term_derivative, factorial = Decimal(0), list(c), Decimal(1)
            for order in range(1, degree + 1):
                term_derivative = _der(term_derivative)
                factorial *= order
                if order >= 2:
                    higher += cabs(ceval(term_derivative, root)) * radius ** order / factorial
            linear = slope * radius
            ratio = (constant + higher) / linear if linear else Decimal("Infinity")
            disks.append({"center_real_decimal": str(root[0]), "center_imag_decimal": str(root[1]),
                          "radius_decimal": str(radius), "rouche_dominance_ratio": float(ratio) if ratio.is_finite() else None,
                          "one_root_numerically_isolated": bool(ratio < 1)})
        disjoint = all(cabs(csub(a, b)) > _d(disks[i]["radius_decimal"]) + _d(disks[j]["radius_decimal"])
                       for i, a in enumerate(roots) for j, b in enumerate(roots) if i < j)
        # Reconstruct the complete polynomial; per-root small residuals alone
        # cannot detect one missing root replaced by a duplicate.
        reconstructed = [(c[-1], Decimal(0))]
        for root in roots:
            product = [zero] * (len(reconstructed) + 1)
            for j, coefficient in enumerate(reconstructed):
                product[j] = csub(product[j], cmul(root, coefficient))
                product[j + 1] = cadd(product[j + 1], coefficient)
            reconstructed = product
        coefficient_scale = max(abs(v) for v in c)
        reconstruction_error = max(cabs(csub(actual, (expected, Decimal(0))))
                                   for actual, expected in zip(reconstructed, c)) / coefficient_scale
        reconstruction_ok = bool(len(reconstructed) == len(c) and reconstruction_error <= Decimal("1e-50"))
        all_isolated = bool(len(roots) == degree and disjoint and all(d["one_root_numerically_isolated"] for d in disks))
        rows = []
        # This distance is diagnostic only; repeated numerator zeros can make
        # ordinary companion estimates inaccurate. The evaluated numerator
        # residual is the authoritative numerical cancellation screen.
        zeros = np.polynomial.polynomial.polyroots(np.array([float(v) for v in n]))
        for root, disk in zip(roots, disks):
            scale = _val([abs(v) for v in c], cabs(root))
            residual = float(cabs(ceval(c, root)) / max(scale, Decimal("1e-150")))
            numerator_scale = _val([abs(v) for v in n], cabs(root))
            numerator_residual = float(cabs(ceval(n, root)) / max(numerator_scale, Decimal("1e-150")))
            numeric_root = complex(float(root[0]), float(root[1]))
            distance = float(np.min(abs(zeros - numeric_root))) if len(zeros) else None
            cancellation = numerator_residual <= 1e-25
            rows.append({"normalized_p_real": float(root[0]), "normalized_p_imag": float(root[1]),
                         "s_real_per_s": float(root[0] * _d(W0)), "s_imag_rad_per_s": float(root[1] * _d(W0)),
                         "oscillation_frequency_hz": float(abs(root[1]) * _d(FP)),
                         "scaled_denominator_residual": residual, "scaled_numerator_at_pole": numerator_residual,
                         "nearest_transmission_zero_distance_normalized": distance,
                         "possible_cancellation": cancellation, "numerical_isolation_disk": disk,
                         "stability": "LHP" if root[0] < _d(-1e-10) else "MARGINAL" if abs(root[0]) <= _d(1e-10) else "RHP"})
        checks = {"denominator_degree_matches_count": len(rows) == degree,
                  "real_sturm_count_matches_isolation": len(real_intervals) == real_count and dc_mult == 0 and gcd_degree == 0,
                  "real_deflation_residuals": all(v <= 1e-60 for v in deflation_residuals),
                  "coefficient_reconstruction": reconstruction_ok,
                  "disjoint_one_root_disks": all_isolated,
                  "individual_denominator_residuals": all(r["scaled_denominator_residual"] <= 1e-25 for r in rows)}
        return {"denominator_degree": degree, "poles": rows, "pole_count": len(rows),
                "denominator_construction": specification,
                "method": "normalized rational ABCD; real Sturm isolation and deflation; simultaneous complex Aberth; Decimal Newton; disjoint Rouche disks and polynomial reconstruction",
                "precision_digits": 160, "distinct_polished_roots": disjoint,
                "real_pole_count": real_count, "real_sturm_sequence_degrees": [len(v) - 1 for v in sequence],
                "real_pole_intervals_decimal": [[str(lo), str(hi)] for lo, hi in real_intervals],
                "real_deflation_scaled_residuals": deflation_residuals,
                "complex_aberth_iterations": iterations,
                "coefficient_reconstruction_relative_error": float(reconstruction_error),
                "root_completeness_checks": checks, "residuals_ok": all(checks.values()),
                "cancellation_candidates": [r for r in rows if r["possible_cancellation"]]}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
