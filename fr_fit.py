"""Least-squares cylinder fit in pure Python - Fusion's interpreter has no numpy.

Equivalent of 3-matic's Fit cylinder (Dlab-IT007 section 5.4, step 2b): the cylinder
that best matches the marked points, whose axis is the anatomical axis of the bone.

Minimises sum((dist(p, axis) - R)^2) over the axis (point + direction, 4 dof) and R.
Levenberg-Marquardt from three starts (the three inertia axes of the points), because
a patch painted on one side of a bone does not have its long axis as the largest
inertia axis - the best of the three wins. No adsk imports: this tests offline.
"""

import math


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    n = _norm(a)
    return (a[0] / n, a[1] / n, a[2] / n)


def _perp_frame(d):
    """Two unit vectors orthogonal to d and to each other."""
    helper = (1.0, 0.0, 0.0) if abs(d[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = _unit(_cross(d, helper))
    return u, _cross(d, u)


def centroid(pts):
    n = float(len(pts))
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n, sum(p[2] for p in pts) / n)


def inertia_axes(pts):
    """Eigenvectors of the covariance matrix, largest eigenvalue first (Jacobi).

    The first one is 3-matic's Line > Fit inertia axes."""
    c = centroid(pts)
    m = [[0.0] * 3 for _ in range(3)]
    for p in pts:
        w = _sub(p, c)
        for i in range(3):
            for j in range(3):
                m[i][j] += w[i] * w[j]
    v = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    for _ in range(50):
        off = max((abs(m[i][j]), i, j) for i in range(3) for j in range(3) if i < j)
        if off[0] < 1e-14:
            break
        _, p, q = off
        theta = 0.5 * math.atan2(2.0 * m[p][q], m[q][q] - m[p][p])
        cs, sn = math.cos(theta), math.sin(theta)
        for k in range(3):                       # m <- m * J
            mkp, mkq = m[k][p], m[k][q]
            m[k][p], m[k][q] = cs * mkp - sn * mkq, sn * mkp + cs * mkq
        for k in range(3):                       # m <- J^T * m
            mpk, mqk = m[p][k], m[q][k]
            m[p][k], m[q][k] = cs * mpk - sn * mqk, sn * mpk + cs * mqk
        for k in range(3):
            vkp, vkq = v[k][p], v[k][q]
            v[k][p], v[k][q] = cs * vkp - sn * vkq, sn * vkp + cs * vkq
    order = sorted(range(3), key=lambda i: -m[i][i])
    return [(_unit((v[0][i], v[1][i], v[2][i])), m[i][i]) for i in order]


def _residuals(pts, a, d, r):
    return [_norm(_cross(_sub(p, a), d)) - r for p in pts]


def _solve(A, b):
    """Gaussian elimination with partial pivoting, small dense system."""
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-30:
            return None
        M[col], M[piv] = M[piv], M[col]
        for r in range(col + 1, n):
            f = M[r][col] / M[col][col]
            for k in range(col, n + 1):
                M[r][k] -= f * M[col][k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (M[r][n] - sum(M[r][k] * x[k] for k in range(r + 1, n))) / M[r][r]
    return x


def _lm(pts, a, d, r, iters=100):
    """Levenberg-Marquardt on (axis point shift s,t; axis tilt al,be; radius)."""
    res = _residuals(pts, a, d, r)
    cost = sum(e * e for e in res)
    lam = 1e-3
    for _ in range(iters):
        u, v = _perp_frame(d)

        def model(x):
            a2 = _add(a, _add(_mul(u, x[0]), _mul(v, x[1])))
            d2 = _unit(_add(d, _add(_mul(u, x[2]), _mul(v, x[3]))))
            return a2, d2, r + x[4]

        h = 1e-6 * max(r, 1e-3)
        cols = []
        for k in range(5):
            x = [0.0] * 5
            x[k] = h
            rk = _residuals(pts, *model(x))
            cols.append([(rk[i] - res[i]) / h for i in range(len(pts))])
        JtJ = [[sum(ci * cj for ci, cj in zip(cols[i], cols[j])) for j in range(5)]
               for i in range(5)]
        Jte = [sum(ci * e for ci, e in zip(cols[i], res)) for i in range(5)]
        improved = False
        for _ in range(10):
            A = [[JtJ[i][j] * (1.0 + lam if i == j else 1.0) for j in range(5)]
                 for i in range(5)]
            step = _solve(A, [-g for g in Jte])
            if step is None:
                lam *= 10.0
                continue
            a2, d2, r2 = model(step)
            res2 = _residuals(pts, a2, d2, r2)
            cost2 = sum(e * e for e in res2)
            if cost2 < cost:
                rel = (cost - cost2) / max(cost, 1e-30)
                a, d, r, res, cost = a2, d2, r2, res2, cost2
                lam = max(lam / 10.0, 1e-12)
                improved = True
                break
            lam *= 10.0
        if not improved or rel < 1e-12:
            break
    return a, d, abs(r), cost


def fit_cylinder(pts, axis_hint=None):
    """Best cylinder through pts (any length unit, result in the same unit).

    axis_hint: start only from this direction instead of the three inertia axes - for
    refits where the axis is already known to be close.

    Returns dict: point (on the axis, at the middle of the points' extent), direction
    (unit), radius, rms, max_abs (residuals), length (extent along the axis), start/end
    (axis points at the extent ends), n, flat (True when every candidate was a 'flat
    patch' cylinder - radius larger than the length it covers - and the least bad one
    was returned).

    A strip marked on one side of a bone is nearly flat along its length, so a huge
    cylinder lying ACROSS it can beat the bone's own axis on residuals. Such a candidate
    (radius > covered length) is never a long-bone axis, so it only wins if nothing
    else is left."""
    if len(pts) < 6:
        raise ValueError('need at least 6 points, got %d' % len(pts))
    c = centroid(pts)
    cands = []
    starts = [_unit(axis_hint)] if axis_hint else [ax for ax, _ in inertia_axes(pts)]
    for d0 in starts:
        r0 = sum(_norm(_cross(_sub(p, c), d0)) for p in pts) / len(pts)
        a, d, r, cost = _lm(pts, c, d0, r0)
        ts = [_dot(_sub(p, a), d) for p in pts]
        cands.append((r > max(ts) - min(ts), cost, a, d, r, min(ts), max(ts)))
    flat, _, a, d, r, t0, t1 = min(cands, key=lambda k: (k[0], k[1]))
    start, end = _add(a, _mul(d, t0)), _add(a, _mul(d, t1))
    res = _residuals(pts, a, d, r)
    return {'point': _mul(_add(start, end), 0.5), 'direction': d, 'radius': r,
            'rms': math.sqrt(sum(e * e for e in res) / len(res)),
            'max_abs': max(abs(e) for e in res), 'length': t1 - t0,
            'start': start, 'end': end, 'n': len(pts), 'flat': flat}


def sample(pts, max_points):
    return pts[::max(1, len(pts) // max_points)]


def fit_slab(pts, p1, p2, max_points=3000, iterations=5, settled_deg=0.01):
    """Cylinder fitted to the part of pts between two points along the bone.

    The slab is bounded by planes perpendicular to the axis through p1 and p2. The
    first axis is the inertia axis of all pts; after each fit the planes are re-cut
    perpendicular to the fitted axis, until it moves less than settled_deg. Refits
    start from the last axis instead of the three inertia starts.

    Returns (fit, slab points, iterations used, inertia axis). Raises ValueError if
    the slab holds too few points."""
    d = inertia_axes(sample(pts, max_points))[0][0]
    inertia = d
    fit, slab, it = None, [], 0
    for it in range(1, iterations + 1):
        lo, hi = sorted((_dot(p1, d), _dot(p2, d)))
        slab = [p for p in pts if lo <= _dot(p, d) <= hi]
        if len(slab) < 12:
            raise ValueError('Only %d surface points between From and To - too few to fit. '
                             'Are the points far enough apart?' % len(slab))
        fit = fit_cylinder(sample(slab, max_points), axis_hint=d if fit else None)
        moved = angle_deg(fit['direction'], d)
        d = fit['direction']
        if moved < settled_deg:
            break
    return fit, slab, it, inertia


def angle_deg(d1, d2):
    """Angle between two axis directions, sign-free (0..90)."""
    c = abs(_dot(_unit(d1), _unit(d2)))
    return math.degrees(math.acos(min(1.0, c)))
