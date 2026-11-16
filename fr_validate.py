"""Checks that a fitted cylinder is (1) the best one for the points and (2) a sound
bone axis. Pure Python, no adsk: runs offline and inside Fusion.

(1) is mathematics: local_optimality perturbs the solution and every perturbation
    must raise the cost. tools/check_scipy.py adds an independent solver.
(2) has no ground truth - Dlab-IT007 5.4 DEFINES the bone axis as this cylinder's axis
    - so the checks are about trustworthiness:
    - slice_centres: the centre of each cross-section along the stretch, and how far
      it sits from the cylinder axis. The numeric form of the PNT's visual check
      ("centred in the cortex along the whole stretch; if it escapes at one end, the
      marking included metaphysis").
    - centre_line: a second, independent axis through those centres.
"""

import math

import fr_fit as F


def _cost(pts, a, d, r):
    return sum(e * e for e in F._residuals(pts, a, F._unit(d), r))


def local_optimality(pts, fit, tilt_deg=0.25, shift_cm=0.01, dr_cm=0.005):
    """Cost after small tilts / shifts of the axis and changes of radius, relative to
    the fitted cost. All ratios > 1 means no nearby cylinder fits better."""
    a, d, r = fit['point'], fit['direction'], fit['radius']
    u, v = F._perp_frame(d)
    base = _cost(pts, a, d, r)
    t = math.tan(math.radians(tilt_deg))
    trials = {}
    for name, w in (('u', u), ('v', v)):
        for s in (1, -1):
            trials['tilt %s%+d' % (name, s)] = _cost(pts, a, F._add(d, F._mul(w, s * t)), r)
            trials['shift %s%+d' % (name, s)] = _cost(pts, F._add(a, F._mul(w, s * shift_cm)), d, r)
    for s in (1, -1):
        trials['radius %+d' % s] = _cost(pts, a, d, r + s * dr_cm)
    ratios = {k: c / base for k, c in trials.items()}
    return {'min_ratio': min(ratios.values()), 'worst': min(ratios, key=ratios.get),
            'tilt_deg': tilt_deg, 'shift_mm': shift_cm * 10, 'dr_mm': dr_cm * 10}


def _circle_2d(xy):
    """Algebraic (Kasa) circle fit: x^2 + y^2 + D x + E y + F = 0."""
    A = [[0.0] * 3 for _ in range(3)]
    b = [0.0] * 3
    for x, y in xy:
        row = (x, y, 1.0)
        rhs = -(x * x + y * y)
        for i in range(3):
            b[i] += row[i] * rhs
            for j in range(3):
                A[i][j] += row[i] * row[j]
    D, E, Fc = F._solve(A, b)
    cx, cy = -D / 2.0, -E / 2.0
    return cx, cy, math.sqrt(max(0.0, cx * cx + cy * cy - Fc))


def slice_centres(pts, fit, n=10):
    """Cut the fitted stretch into n slices along the axis. For each: the centre of the
    circle that best fits that slice alone, its distance from the cylinder axis, and its
    radius. Centres far off the axis at one end = the marking took in metaphysis."""
    a, d = fit['point'], fit['direction']
    u, v = F._perp_frame(d)
    half = fit['length'] / 2.0
    rows = []
    for k in range(n):
        t0 = -half + k * (2 * half / n)
        t1 = t0 + 2 * half / n
        xy = []
        for p in pts:
            w = F._sub(p, a)
            t = F._dot(w, d)
            if t0 <= t < t1:
                xy.append((F._dot(w, u), F._dot(w, v)))
        if len(xy) < 8:
            continue
        cx, cy, r = _circle_2d(xy)
        tm = (t0 + t1) / 2.0
        centre = F._add(a, F._add(F._mul(d, tm), F._add(F._mul(u, cx), F._mul(v, cy))))
        rows.append({'t_mm': tm * 10, 'offset_mm': math.hypot(cx, cy) * 10,
                     'r_mm': r * 10, 'n': len(xy), 'centre': centre})
    return rows


def centre_line(rows, fit):
    """Line through the slice centres (their inertia axis): an axis found without any
    cylinder. Returns its angle to the cylinder axis and the slice centres' scatter
    about it."""
    cs = [r['centre'] for r in rows]
    d = F.inertia_axes(cs)[0][0]
    c = F.centroid(cs)
    scatter = [F._norm(F._cross(F._sub(p, c), d)) * 10 for p in cs]
    return {'angle_deg': F.angle_deg(d, fit['direction']),
            'max_scatter_mm': max(scatter), 'slices': len(cs)}


def summary(pts, fit, n_slices=10):
    rows = slice_centres(pts, fit, n_slices)
    return {'optimality': local_optimality(pts, fit),
            'slices': [{k: round(v, 3) for k, v in r.items() if k != 'centre'} for r in rows],
            'max_centre_offset_mm': max(r['offset_mm'] for r in rows),
            'end_offsets_mm': (rows[0]['offset_mm'], rows[-1]['offset_mm']),
            'centre_line': centre_line(rows, fit)}
