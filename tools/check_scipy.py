"""Independent check of fr_fit: refit the same points with scipy from random starts.

    py -3.10 tools/check_scipy.py points.json [more.json ...]

points.json: {"name": ..., "points": [[x,y,z], ...], "fit": {...fr_fit result...}}
(written by a bridge job). If fr_fit found the best cylinder, scipy's best start lands
on the same axis and radius, and no start finds a lower cost.
"""

import json
import math
import sys

import numpy as np
from scipy.optimize import least_squares


def direction(theta, phi):
    return np.array([math.sin(theta) * math.cos(phi), math.sin(theta) * math.sin(phi),
                     math.cos(theta)])


def frame(d):
    h = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(d, h)
    u /= np.linalg.norm(u)
    return u, np.cross(d, u)


def residuals(x, P, c):
    theta, phi, s, t, r = x
    d = direction(theta, phi)
    u, v = frame(d)
    a = c + s * u + t * v
    return np.linalg.norm(np.cross(P - a, d), axis=1) - r


def check(path, starts=20, seed=0):
    job = json.load(open(path, encoding='utf-8'))
    P = np.array(job['points'])
    c = P.mean(axis=0)
    rng = np.random.default_rng(seed)
    best = None
    for k in range(starts):
        d0 = rng.normal(size=3)
        d0 /= np.linalg.norm(d0)
        if d0[2] < 0:
            d0 = -d0
        x0 = [math.acos(d0[2]), math.atan2(d0[1], d0[0]), 0.0, 0.0,
              float(np.mean(np.linalg.norm(np.cross(P - c, d0), axis=1)))]
        sol = least_squares(residuals, x0, args=(P, c), method='lm', xtol=1e-12, ftol=1e-12)
        cost = float(np.sum(sol.fun ** 2))
        if best is None or cost < best[0]:
            best = (cost, sol.x)
    cost, x = best
    d = direction(x[0], x[1])
    u, v = frame(d)
    a = c + x[2] * u + x[3] * v
    f = job['fit']
    fd = np.array(f['direction'])
    fa = np.array(f['point'])
    fr = np.array(residuals_fr(P, fa, fd, f['radius']))
    angle = math.degrees(math.acos(min(1.0, abs(float(np.dot(d, fd))))))
    offset = float(np.linalg.norm(np.cross(fa - a, d)))
    print('%-14s scipy best of %d starts vs fr_fit:  axis %.4f deg apart, %.4f mm apart, '
          'R %.4f vs %.4f mm, cost %.6g vs %.6g (%+.3f%%)'
          % (job['name'], starts, angle, offset * 10, abs(x[4]) * 10, f['radius'] * 10,
             cost, float(np.sum(fr ** 2)), 100 * (float(np.sum(fr ** 2)) - cost) / cost))


def residuals_fr(P, a, d, r):
    d = d / np.linalg.norm(d)
    return np.linalg.norm(np.cross(P - a, d), axis=1) - r


if __name__ == '__main__':
    for p in sys.argv[1:]:
        check(p)
