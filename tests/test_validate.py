"""Offline checks of fr_validate and fr_fit.fit_slab.  py -3.10 tests/test_validate.py"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fr_fit as F  # noqa: E402
import fr_validate as V  # noqa: E402


def tube(radius_at, centre_at, length, n, seed=3):
    """Surface points of a tube along z, z in [0, length]; radius and centre vary with z."""
    rnd = random.Random(seed)
    pts = []
    for _ in range(n):
        z = rnd.uniform(0, length)
        th = rnd.uniform(0, 2 * math.pi)
        cx, cy = centre_at(z)
        r = radius_at(z)
        pts.append((cx + r * math.cos(th), cy + r * math.sin(th), z))
    return pts


fails = 0


def report(name, ok, msg):
    global fails
    fails += not ok
    print('%-34s %s  %s' % (name, 'OK  ' if ok else 'FAIL', msg))


# 1. a perfect cylinder: optimal, centred everywhere, centre line = axis
pts = tube(lambda z: 0.65, lambda z: (0.0, 0.0), 10.0, 3000)
fit = F.fit_cylinder(pts)
s = V.summary(pts, fit)
report('perfect cylinder', s['optimality']['min_ratio'] > 1.0 and
       s['max_centre_offset_mm'] < 0.05 and s['centre_line']['angle_deg'] < 0.1,
       'min cost ratio %.4f, max centre offset %.3f mm, centre line %.3f deg'
       % (s['optimality']['min_ratio'], s['max_centre_offset_mm'], s['centre_line']['angle_deg']))

# 2. a diaphysis with a flaring metaphysis at the top: marking into the flare shows
#    up as a large centre offset / radius at that end
flare = lambda z: 0.65 + (0.25 * ((z - 8.0) / 2.0) ** 2 if z > 8.0 else 0.0)
off_centre = lambda z: ((0.15 * ((z - 8.0) / 2.0) ** 2, 0.0) if z > 8.0 else (0.0, 0.0))
pts = tube(flare, off_centre, 10.0, 6000)
good, _, _, _ = F.fit_slab(pts, (0, 0, 2.0), (0, 0, 7.5))
bad, slab_bad, _, _ = F.fit_slab(pts, (0, 0, 2.0), (0, 0, 10.0))
sg = V.summary([p for p in pts if 2.0 <= p[2] <= 7.5], good)
sb = V.summary(slab_bad, bad)
report('flare left out (2-7.5)', sg['max_centre_offset_mm'] < 0.1,
       'max centre offset %.3f mm' % sg['max_centre_offset_mm'])
# the cylinder also tilts toward the flare, so both ends move; the flared one more
report('flare marked in (2-10)', sb['end_offsets_mm'][1] > sb['end_offsets_mm'][0] and
       sb['end_offsets_mm'][1] > 0.3 and sb['optimality']['min_ratio'] > 1.0,
       'end offsets %.3f / %.3f mm; axis tilted %.2f deg off the true one (vs %.3f clean)'
       % (sb['end_offsets_mm'] + (F.angle_deg(bad['direction'], (0, 0, 1)),
                                  F.angle_deg(good['direction'], (0, 0, 1)))))

# 3. a bowed bone: centres trace the bow
bow = lambda z: (0.3 * math.sin(math.pi * z / 10.0), 0.0)
pts = tube(lambda z: 0.65, bow, 10.0, 6000)
fit = F.fit_cylinder(pts)
s = V.summary(pts, fit)
report('bowed tube (3 mm bow)', s['max_centre_offset_mm'] > 0.5,
       'max centre offset %.3f mm, profile %s'
       % (s['max_centre_offset_mm'], [round(r['offset_mm'], 2) for r in s['slices']]))

raise SystemExit(1 if fails else 0)
