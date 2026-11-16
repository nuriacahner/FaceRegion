"""Offline checks of fr_fit against cylinders with a known answer.  py -3.10 tests/test_fit.py"""

import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fr_fit  # noqa: E402


def sample(axis_pt, axis_dir, r, length, n, arc_deg=360.0, noise=0.0, seed=1):
    rnd = random.Random(seed)
    d = fr_fit._unit(axis_dir)
    u, v = fr_fit._perp_frame(d)
    pts = []
    for _ in range(n):
        th = math.radians(rnd.uniform(0.0, arc_deg))
        t = rnd.uniform(-length / 2, length / 2)
        rr = r + rnd.gauss(0.0, noise)
        p = fr_fit._add(axis_pt, fr_fit._add(fr_fit._mul(d, t),
            fr_fit._add(fr_fit._mul(u, rr * math.cos(th)), fr_fit._mul(v, rr * math.sin(th)))))
        pts.append(p)
    return pts


def dist_point_line(p, a, d):
    return fr_fit._norm(fr_fit._cross(fr_fit._sub(p, a), d))


CASES = [
    # name, axis point, axis dir, R, length, n, arc, noise   (cm, like Fusion)
    ('full, exact', (8.0, 7.0, -104.0), (0.1, 0.2, 1.0), 0.6, 6.0, 800, 360, 0.0),
    ('full, 0.02 noise', (8.0, 7.0, -104.0), (0.3, -0.1, 1.0), 0.6, 6.0, 1500, 360, 0.02),
    ('half arc (one side painted)', (8.0, 7.0, -104.0), (0.0, 0.4, 1.0), 0.6, 4.0, 800, 180, 0.01),
    ('short and wide (L < 2R)', (0.0, 0.0, 0.0), (1.0, 1.0, 0.0), 1.0, 1.2, 800, 360, 0.005),
    # one face of a 6-patch bone: a long strip, a quarter of the way round
    ('90 deg strip, one side', (8.0, 7.0, -104.0), (0.2, 0.1, 1.0), 0.65, 10.0, 1500, 90, 0.03),
]

fails = 0
for name, a, d, r, L, n, arc, noise in CASES:
    pts = sample(a, d, r, L, n, arc, noise)
    t0 = time.time()
    f = fr_fit.fit_cylinder(pts)
    dt = time.time() - t0
    ang = fr_fit.angle_deg(f['direction'], d)
    off = dist_point_line(a, f['point'], f['direction'])
    tol = 0.05 + 50 * noise          # degrees
    ok = ang < tol and abs(f['radius'] - r) < 0.01 + 3 * noise and off < 0.01 + 3 * noise
    fails += not ok
    print('%-30s %s  angle %.4f deg  R %.4f (true %.2f)  axis offset %.4f  rms %.4f  %.2fs'
          % (name, 'OK  ' if ok else 'FAIL', ang, f['radius'], r, off, f['rms'], dt))

ax = fr_fit.inertia_axes(sample((0, 0, 0), (0, 0, 1), 0.5, 10.0, 500))[0][0]
ok = fr_fit.angle_deg(ax, (0, 0, 1)) < 1.0
fails += not ok
print('%-30s %s' % ('inertia axis of a long tube', 'OK' if ok else 'FAIL'))
raise SystemExit(1 if fails else 0)
