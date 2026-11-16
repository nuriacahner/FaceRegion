"""Draw the toolbar icons (a cylinder over a strip of facets). Pure Python PNG writer.

    py -3.10 tools/make_icons.py
"""

import math
import os
import struct
import zlib

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'resources', 'FaceRegion')
BLUE = (30, 140, 255)
GREY = (120, 120, 120)


def png(path, size, px):
    raw = b''.join(b'\x00' + bytes(c for p in row for c in p) for row in px)

    def chunk(tag, data):
        return (struct.pack('>I', len(data)) + tag + data
                + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))

    with open(path, 'wb') as fh:
        fh.write(b'\x89PNG\r\n\x1a\n')
        fh.write(chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)))
        fh.write(chunk(b'IDAT', zlib.compress(raw, 9)))
        fh.write(chunk(b'IEND', b''))


def draw(size):
    ss = 4                                   # supersampling for soft edges
    n = size * ss
    cov = [[None] * n for _ in range(n)]
    cx, rx, ry = n * 0.5, n * 0.30, n * 0.11
    top, bot = n * 0.18, n * 0.70
    w = max(1.0, n / 16.0)
    for y in range(n):
        for x in range(n):
            dx = (x + 0.5 - cx) / rx
            # facet strip under the cylinder: a zigzag of triangles
            if y > n * 0.80:
                k = (x / (n / 4.0)) % 1.0
                if abs((y - n * 0.80) / (n * 0.18) - abs(2 * k - 1)) < w / (n * 0.18):
                    cov[y][x] = GREY
            if abs(dx) > 1.0 + w / rx:
                continue
            h = ry * math.sqrt(max(0.0, 1.0 - dx * dx))
            on_top = abs(abs(y + 0.5 - top) - h) < w * 0.8
            on_bot = (y + 0.5 > bot) and abs(y + 0.5 - bot - h) < w * 0.8
            on_side = abs(abs(x + 0.5 - cx) - rx) < w * 0.8 and top <= y <= bot
            inside = abs(dx) < 1.0 and top <= y + 0.5 <= bot + h
            if on_top or on_bot or on_side:
                cov[y][x] = BLUE
            elif inside and cov[y][x] is None:
                cov[y][x] = (200, 225, 255)
    px = []
    for y in range(size):
        row = []
        for x in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(ss):
                for sx in range(ss):
                    c = cov[y * ss + sy][x * ss + sx]
                    if c:
                        acc[0] += c[0]
                        acc[1] += c[1]
                        acc[2] += c[2]
                        acc[3] += 1
            a = acc[3]
            row.append((acc[0] // a, acc[1] // a, acc[2] // a, 255 * a // (ss * ss))
                       if a else (0, 0, 0, 0))
        px.append(row)
    return px


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for s in (16, 32, 64):
        png(os.path.join(OUT, '%dx%d.png' % (s, s)), s, draw(s))
    print('icons written to', OUT)
