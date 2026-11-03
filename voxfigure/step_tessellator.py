"""Tessellate STEP file into per-solid meshes.

Classification uses the inner bounding box: solids extending beyond = outer.
"""

import os

import cadquery as cq
import numpy as np
from .part_config import get_part_config

# Tessellating a STEP via cadquery costs ~1.5s; the result is a pure function
# of (file content, params), so memoize it. Keyed on the file's mtime+size so
# an edited STEP re-tessellates. Bounded LRU (hits refresh recency) so a
# long-running server with many distinct files doesn't grow without limit;
# 32 fits a full model set (parts + for-print + armor) without thrashing.
_tess_cache = {}
_TESS_CACHE_MAX = 32


def _tess_cache_key(step_file, pixel_size, part, model_type, inner_box):
    st = os.stat(step_file)
    box = tuple(map(tuple, inner_box)) if inner_box else None
    return (os.path.realpath(step_file), st.st_mtime_ns, st.st_size,
            pixel_size, part, model_type, box)


def tessellate_step(step_file: str, pixel_size: float = 2.5,
                    part: str = "head", model_type: str = "steve",
                    inner_box=None):
    """Tessellate each solid and classify as inner/outer.

    Args:
        inner_box: optional [min, max] override, e.g. [[-5,-10,-32],[5,10,0]]
    """
    try:
        cache_key = _tess_cache_key(step_file, pixel_size, part, model_type, inner_box)
    except OSError:
        cache_key = None
    cached = _tess_cache.pop(cache_key, None) if cache_key is not None else None
    if cached is not None:
        _tess_cache[cache_key] = cached      # re-insert at the end: most recently used
    else:
        cached = _tessellate_step_uncached(step_file, pixel_size, part, model_type, inner_box)
        if cache_key is not None:
            while len(_tess_cache) >= _TESS_CACHE_MAX:
                try:
                    _tess_cache.pop(next(iter(_tess_cache)))   # evict least recently used
                except (KeyError, StopIteration):              # lost a race with another thread
                    break
            _tess_cache[cache_key] = cached
    # Shallow-copy each solid dict: callers reassign s["id"], and the large
    # positions/normals lists are read-only, so sharing them is safe and cheap.
    return [dict(s) for s in cached]


def _tessellate_step_uncached(step_file, pixel_size, part, model_type, inner_box):
    pc = get_part_config(part, model_type, pixel_size)
    if inner_box:
        inner_min = np.array(inner_box[0])
        inner_max = np.array(inner_box[1])
    else:
        inner_min = np.array(pc["inner_box_min"])
        inner_max = np.array(pc["inner_box_max"])
    box_tol = pixel_size * 0.02

    print(f"Part '{part}': grid={pc['grid']}, center={pc['center_mm']}")
    print(f"Inner box: {inner_min.tolist()} → {inner_max.tolist()}")

    shape = cq.importers.importStep(step_file)
    cq_solids = shape.solids().vals()
    print(f"Loaded {len(cq_solids)} solids")

    result = []
    counts = {"inner": 0, "outer": 0}

    for idx, cq_solid in enumerate(cq_solids):
        bb = cq_solid.BoundingBox()
        cx, cy, cz = (bb.xmin+bb.xmax)/2, (bb.ymin+bb.ymax)/2, (bb.zmin+bb.zmax)/2
        sx, sy, sz = bb.xmax-bb.xmin, bb.ymax-bb.ymin, bb.zmax-bb.zmin

        solid_min = np.array([bb.xmin, bb.ymin, bb.zmin])
        solid_max = np.array([bb.xmax, bb.ymax, bb.zmax])

        extends_outside = np.any(solid_min < inner_min - box_tol) or \
                          np.any(solid_max > inner_max + box_tol)
        layer = "outer" if extends_outside else "inner"
        counts[layer] += 1

        verts, faces = cq_solid.tessellate(0.1)
        positions, normals = [], []
        for tri in faces:
            v0, v1, v2 = tri
            p0 = [verts[v0].x, verts[v0].y, verts[v0].z]
            p1 = [verts[v1].x, verts[v1].y, verts[v1].z]
            p2 = [verts[v2].x, verts[v2].y, verts[v2].z]
            e1, e2 = np.array(p1)-np.array(p0), np.array(p2)-np.array(p0)
            n = np.cross(e1, e2)
            nl = np.linalg.norm(n)
            n = (n / nl) if nl > 0 else np.array([0, 0, 1])
            for p in [p0, p1, p2]:
                positions.extend([round(p[0],3), round(p[1],3), round(p[2],3)])
                normals.extend([round(float(n[0]),3), round(float(n[1]),3), round(float(n[2]),3)])

        result.append({
            "id": idx,
            "center": [round(cx,3), round(cy,3), round(cz,3)],
            "size": [round(sx,3), round(sy,3), round(sz,3)],
            "bbox_min": [round(bb.xmin,3), round(bb.ymin,3), round(bb.zmin,3)],
            "bbox_max": [round(bb.xmax,3), round(bb.ymax,3), round(bb.zmax,3)],
            "layer_guess": layer,
            "positions": positions,
            "normals": normals,
            "tri_count": len(faces),
        })

    print(f"Classification: inner={counts['inner']}, outer={counts['outer']}")
    return result
