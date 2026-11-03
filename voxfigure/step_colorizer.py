"""Shared logic for coloring STEP solids from skin texture.

Supports all body parts with different grid dimensions and center offsets.

The per-triangle work (surface classification, grid snapping, skin sampling,
flat-array building) is vectorized with numpy. The scalar helpers
`_pos_to_index` / `_is_on_surface` support individual point and surface lookups.
"""

import numpy as np
from collections import Counter
from .part_config import get_part_config, make_grid

# Face order encodes the same priority as _is_on_surface's short-circuit:
# a triangle matching several faces (chamfer corner) takes the first.
_FACES = ("front", "back", "left", "right", "top", "bottom")


def _pos_to_index(pos, grid):
    """Snap a 3D position to nearest grid index on each axis."""
    result = []
    for ax in range(3):
        distances = np.abs(np.asarray(grid[ax], dtype=float) - pos[ax])
        # Uniform scaling can turn an exact midpoint into values a few ulps
        # apart. Treat numerical ties as ties and retain the historical
        # first-index tie-break so texture lookup is scale-invariant.
        result.append(int(np.flatnonzero(
            distances <= distances.min() + 1e-9)[0]))
    return tuple(result)


def _is_on_surface(tri_center, normal, box_min, box_max, tol):
    """Check if a triangle lies on one of the 6 bounding box surfaces."""
    tcx, tcy, tcz = tri_center
    nx, ny, nz = normal
    if abs(tcx - box_max[0]) < tol and nx > 0.5: return "front"
    if abs(tcx - box_min[0]) < tol and nx < -0.5: return "back"
    if abs(tcy - box_max[1]) < tol and ny > 0.5: return "left"
    if abs(tcy - box_min[1]) < tol and ny < -0.5: return "right"
    if abs(tcz - box_max[2]) < tol and nz > 0.5: return "top"
    if abs(tcz - box_min[2]) < tol and nz < -0.5: return "bottom"
    return None


def _solid_arrays(s):
    """Cached float64 (m,3) vertex-major views of a solid's positions/normals.

    The geometry cache shares solid dicts across requests and their
    positions/normals lists are never mutated in place (tessellate_step
    contract), so memoizing the list→array conversion on the dict is safe and
    lets repeat generations skip it entirely. The arrays are write-protected so
    a future in-place edit fails loudly instead of corrupting the cache."""
    cached = s.get("_nparr")
    if cached is None:
        pos = s.get("positions") or []
        nrm = s.get("normals") or []
        P = np.asarray(pos[:len(pos) // 3 * 3], dtype=np.float64).reshape(-1, 3)
        N = np.asarray(nrm[:len(nrm) // 3 * 3], dtype=np.float64).reshape(-1, 3)
        P.setflags(write=False)
        N.setflags(write=False)
        cached = s["_nparr"] = (P, N)
    return cached


def _classify_faces(tc, nv, bmin, bmax, tol):
    """Vectorized _is_on_surface: per-triangle face id 0-5 (index into _FACES),
    -1 when not on any box surface. `tc` = (n,3) triangle centers, `nv` = (n,3)
    first-vertex normals. np.select keeps the same first-match priority."""
    conds = [
        (np.abs(tc[:, 0] - bmax[0]) < tol) & (nv[:, 0] > 0.5),
        (np.abs(tc[:, 0] - bmin[0]) < tol) & (nv[:, 0] < -0.5),
        (np.abs(tc[:, 1] - bmax[1]) < tol) & (nv[:, 1] > 0.5),
        (np.abs(tc[:, 1] - bmin[1]) < tol) & (nv[:, 1] < -0.5),
        (np.abs(tc[:, 2] - bmax[2]) < tol) & (nv[:, 2] > 0.5),
        (np.abs(tc[:, 2] - bmin[2]) < tol) & (nv[:, 2] < -0.5),
    ]
    return np.select(conds, range(6), default=-1)


def _snap_indices(coords, g_arrs):
    """Vectorized _pos_to_index over N points → (n,3) int indices. argmin
    returns the first minimum, matching the scalar min()'s tie-break."""
    out = np.empty((len(coords), 3), dtype=np.intp)
    for ax in range(3):
        distances = np.abs(coords[:, ax, None] - g_arrs[ax][None, :])
        minima = distances.min(axis=1, keepdims=True)
        out[:, ax] = (distances <= minima + 1e-9).argmax(axis=1)
    return out


def outer_occupancy(outer_solids, part, model_type, pixel_size):
    """Set of (ix,iy,iz) outer-grid cells covered by the real hat SHELL for `part`.

    Only triangles ON the outer part-boundary count (via the vectorized
    `_is_on_surface` test). This is the crucial filter: `color_solids` keeps
    oversized structural CONNECTOR solids (thousands of triangles) that overlap
    the inner interior — counting their every centroid would snap to hundreds of
    cells and falsely bury visible inner faces. The hat shell's faces sit on the
    outer box surface; a connector's interior faces don't, so they're excluded.
    Same grid dims/center as inner → indices are directly comparable between layers."""
    pc = get_part_config(part, model_type, pixel_size)
    grid = pc["grid"]; ps = pc["pixel_size"]; expand_px = pc.get("outer_expand", 0.25)
    outer_vs = [(grid[i] + 2 * expand_px) * ps / grid[i] for i in range(3)]
    g_arrs = [np.asarray(a) for a in make_grid(grid, pc["center_mm"], outer_vs)]
    bmin, bmax = pc["outer_box_min"], pc["outer_box_max"]
    tol = ps * 0.2
    occ = set()
    for s in outer_solids:
        if not s.get("normals"):        # no normals → nothing classifies as surface
            continue
        P, N = _solid_arrays(s)
        n_tris = len(P) // 3
        if not n_tris:
            continue
        T = P[:n_tris * 3].reshape(n_tris, 3, 3)
        tc = (T[:, 0] + T[:, 1] + T[:, 2]) / 3.0
        on = _classify_faces(tc, N[0::3][:n_tris], bmin, bmax, tol) >= 0
        if on.any():                    # hat shell only, not connector interior
            occ.update(map(tuple, _snap_indices(tc[on], g_arrs).tolist()))
    return occ


def _quantize_color_indices(all_colors, max_colors):
    """Return ``(palette, indices, palette_norm)`` without expanding colours.

    ``indices`` is a numpy array with one palette index per vertex. When the
    input already fits in ``max_colors``, ``palette_norm`` is ``None`` so the
    compatibility wrapper below can preserve the caller's original float
    values byte-for-byte. Keeping this compact path separate matters for the
    main 3D preview: expanding a million palette indices back into three Python
    floats per vertex used hundreds of MB just before JSON serialization.
    """
    from .detail_palette import quantize_rgb
    arr = np.asarray(all_colors, dtype=np.float64).reshape(-1, 3)*255
    palette, nearest = quantize_rgb(arr, max_colors)
    # Preserve the historical no-op return for already fitting palettes.
    rounded = np.floor(np.clip(arr,0,255)+.5).astype(np.int64)
    codes = (rounded[:,0]<<16)|(rounded[:,1]<<8)|rounded[:,2]
    if len(np.unique(codes))<=max_colors:
        return palette, nearest, None
    pal_norm = np.round(np.asarray(palette,dtype=np.float64)/255.0,4)
    return palette, nearest, pal_norm


def quantize_color_indices(all_colors, max_colors):
    """Quantize colours and return a compact palette + numpy index array."""
    palette, nearest, _palette_norm = _quantize_color_indices(all_colors, max_colors)
    return palette, nearest


def quantize_colors(all_colors, max_colors):
    """Quantize flat [r,g,b,...] (0-1) to max_colors.

    Returns (remapped, palette, nearest_indices). The expanded return format is
    retained for compatibility; large previews should use
    :func:`quantize_color_indices` to avoid materializing RGB triples.
    """
    palette, nearest, palette_norm = _quantize_color_indices(all_colors, max_colors)
    if palette_norm is None:
        return all_colors, palette, nearest.tolist()
    remapped = palette_norm[nearest].ravel().tolist()
    return remapped, palette, nearest.tolist()


def color_solids(solids, skin, pixel_size, part, model_type="steve",
                 mode="face", max_colors=8, inner_box=None,
                 skip_quantize=False, drop_untextured_outer=False, texture_scale=1,
                 include_texture_faces=False):
    """Color STEP solids from skin texture. Supports all body parts.

    Args:
        solids: list of dicts with 'layer', 'center', 'positions', 'normals'
        skin: SkinParser instance
        pixel_size: inner pixel size in mm
        part: body part name (head/body/right_arm/etc)
        model_type: steve or alex
        mode: 'body' or 'face'
        max_colors: palette size limit
        skip_quantize: if True, skip color quantization (caller handles it)
        texture_scale: texels per canonical skin pixel; physical dimensions stay fixed
        include_texture_faces: attach per-triangle UV-face ids (or -1 for fallback
            colour) for surface selection, without changing display/3MF colours
    """
    if texture_scale not in (1, 2):
        raise ValueError('Unsupported skin texture scale')
    pc = get_part_config(part, model_type, pixel_size)
    grid = tuple(n * texture_scale for n in pc["grid"])
    part_dims = tuple(n * texture_scale for n in pc["part_dims"])
    ps = pc["pixel_size"]
    texel_mm = ps / texture_scale
    sample_kw = {'texture_scale': texture_scale} if texture_scale != 1 else {}
    surface_tol = ps * 0.2
    expand_px = pc.get("outer_expand", 0.25)
    expand_mm = expand_px * ps

    # Classification boxes (for _is_on_surface detection)
    if inner_box:
        inner_box_min, inner_box_max = list(inner_box[0]), list(inner_box[1])
        outer_box_min = [inner_box[0][i] - expand_mm for i in range(3)]
        outer_box_max = [inner_box[1][i] + expand_mm for i in range(3)]
    else:
        inner_box_min, inner_box_max = pc["inner_box_min"], pc["inner_box_max"]
        outer_box_min, outer_box_max = pc["outer_box_min"], pc["outer_box_max"]

    # UV grid — ALWAYS uses standard center from PART_OFFSETS + pixel_size spacing
    # This is independent of the classification box
    std_center = pc["center_mm"]  # from PART_OFFSETS * pixel_size (before box override)
    inner_grid = make_grid(grid, std_center, [texel_mm, texel_mm, texel_mm])

    # Outer grid: standard outer voxel sizes per axis
    outer_total = [(pc["grid"][i] + 2 * expand_px) * ps for i in range(3)]
    outer_vs = [outer_total[i] / grid[i] for i in range(3)]
    outer_grid = make_grid(grid, std_center, outer_vs)

    inner_g_arrs = [np.asarray(a) for a in inner_grid]
    outer_g_arrs = [np.asarray(a) for a in outer_grid]

    # ─── Pass 1: scan all solids, collect skin colors ───
    # Per kept solid: (textured_mask, tri_rgb_q, first_vertex_normals, color_weights, n_tris)
    solid_tri_infos = []
    texture_faces = []
    delete_indices = []
    global_skin_colors = Counter()
    # Size threshold: solids bigger than this on any axis are likely connection pieces
    conn_threshold = texel_mm * 2.0

    for si, s in enumerate(solids):
        layer = s.get("layer", "inner")
        g = inner_grid if layer == "inner" else outer_grid
        g_arrs = inner_g_arrs if layer == "inner" else outer_g_arrs
        bmin = inner_box_min if layer == "inner" else outer_box_min
        bmax = inner_box_max if layer == "inner" else outer_box_max
        positions = s.get("positions", [])
        normals = s.get("normals", [])
        n_tris = len(positions) // 9

        solid_center = s.get("center", [0, 0, 0])
        solid_grid = _pos_to_index(solid_center, g)

        # Per-solid: detect if this is a multi-cell solid (larger than standard voxel)
        # Multi-cell → per-triangle grid (accurate per-pixel)
        # Single-cell → per-solid center (avoids stripe artifacts)
        bbox_min_s = s.get("bbox_min")
        bbox_max_s = s.get("bbox_max")
        if not bbox_min_s or not bbox_max_s:
            xs = positions[0::3]; ys = positions[1::3]; zs = positions[2::3]
            if xs:
                bbox_min_s = [min(xs), min(ys), min(zs)]
                bbox_max_s = [max(xs), max(ys), max(zs)]
            else:
                bbox_min_s = bbox_max_s = solid_center
        max_dim = max(bbox_max_s[i] - bbox_min_s[i] for i in range(3))
        use_per_triangle = max_dim > conn_threshold

        if use_per_triangle or n_tris > 64:
            # ── Vectorized path: multi-cell connectors / face sheets (hundreds to
            # tens of thousands of triangles) — classification, grid snapping and
            # skin sampling all run as array ops.
            P, N = _solid_arrays(s)
            T = P[:n_tris * 3].reshape(n_tris, 3, 3)
            nv = N[0::3][:n_tris]                    # first-vertex normal per triangle
            tc = (T[:, 0] + T[:, 1] + T[:, 2]) / 3.0
            face_id = _classify_faces(tc, nv, bmin, bmax, surface_tol)
            has_surface_tri = bool((face_id >= 0).any())

            # Sample the skin per face direction (one batch per face instead of
            # one call per triangle). rgba stays (0,0,0,0) off-surface.
            rgba = np.zeros((n_tris, 4), dtype=np.uint8)
            for f in range(6):
                m = face_id == f
                if not m.any():
                    continue
                if use_per_triangle:
                    idx = _snap_indices(tc[m], g_arrs)
                    rgba[m] = skin.get_face_colors_batch(part, layer, _FACES[f],
                                                         idx[:, 0], idx[:, 1], idx[:, 2],
                                                         part_dims, **sample_kw)
                else:
                    rgba[m] = skin.get_face_color(part, layer, _FACES[f], *solid_grid, part_dims, **sample_kw)
            textured = (face_id >= 0) & (rgba[:, 3] > 0)
            if include_texture_faces:
                texture_faces.append(np.where(textured, face_id, -1).tolist())
            tri_rgb_q = np.round(rgba[:, :3].astype(np.float64) / 255.0, 4)

            # Per-colour vote toward the solid's dominant colour (used in body mode
            # and as the face-mode fallback). Side faces (front/back/left/right) are
            # the real pixels; top/bottom are end caps — the part's under/over-side,
            # usually painted to blend with the neighbouring part (e.g. the torso
            # bottom matches the legs). Weight those down so a voxel takes its front
            # colour, not the underside one.
            color_weights = {}
            global_add = []
            if textured.any():
                uniq, first, inv = np.unique(tri_rgb_q[textured], axis=0,
                                             return_index=True, return_inverse=True)
                # Reorder unique colors to FIRST-OCCURRENCE order: dict insertion
                # order then matches the old per-triangle Counter, which pass 2's
                # max() tie-break and most_common() depend on.
                order = np.argsort(first, kind="stable")
                remap = np.empty(len(order), dtype=np.intp)
                remap[order] = np.arange(len(order))
                inv = remap[inv]
                w = np.where(np.isin(face_id[textured], (4, 5)), 0.15, 1.0)  # top/bottom
                sums = np.bincount(inv, weights=w, minlength=len(order))
                counts = np.bincount(inv, minlength=len(order))
                keys = [tuple(c) for c in uniq[order].tolist()]
                color_weights = dict(zip(keys, sums.tolist()))
                global_add = list(zip(keys, counts.tolist()))
            payload = ("vec", textured, tri_rgb_q, nv, color_weights, n_tris)
        else:
            # ── Scalar path: single-cell voxels (~12 triangles). The per-solid
            # numpy overhead exceeds the whole loop here, so the original
            # per-triangle code is kept for them. One color lookup per face
            # (the grid index is the solid center for single-cell solids).
            has_surface_tri = False
            tri_info = []
            tri_faces = []
            color_weights = Counter()
            for t in range(n_tris):
                pi = t * 9
                nx, ny, nz = normals[pi], normals[pi+1], normals[pi+2]
                tcx = (positions[pi]+positions[pi+3]+positions[pi+6])/3
                tcy = (positions[pi+1]+positions[pi+4]+positions[pi+7])/3
                tcz = (positions[pi+2]+positions[pi+5]+positions[pi+8])/3

                face_dir = _is_on_surface([tcx,tcy,tcz], [nx,ny,nz], bmin, bmax, surface_tol)
                tri_faces.append(-1)
                if face_dir:
                    has_surface_tri = True
                    rgba = skin.get_face_color(part, layer, face_dir, *solid_grid, part_dims, **sample_kw)
                    if rgba[3] > 0:
                        tri_faces[-1] = _FACES.index(face_dir)
                        rgb = [round(int(rgba[0])/255,4), round(int(rgba[1])/255,4), round(int(rgba[2])/255,4)]
                        tri_info.append(rgb)
                        color_weights[tuple(rgb)] += 0.15 if face_dir in ("top", "bottom") else 1.0
                    else:
                        tri_info.append(None)
                else:
                    tri_info.append(None)
            global_add = [(tuple(c), 1) for c in tri_info if c]
            payload = ("py", tri_info, color_weights, n_tris)
            if include_texture_faces:
                texture_faces.append(tri_faces)

        if layer == "outer" and has_surface_tri and not global_add:
            is_oversized = max_dim > conn_threshold
            overlaps_inner = all(
                bbox_min_s[i] < inner_box_max[i] and bbox_max_s[i] > inner_box_min[i]
                for i in range(3)
            ) if is_oversized else False

            # Preserve oversized structural connectors that overlap the inner body.
            # Untextured second-layer sheets can also satisfy that size/overlap test;
            # drop_untextured_outer removes them instead of retaining an empty shell.
            if drop_untextured_outer or not (is_oversized and overlaps_inner):
                delete_indices.append(si)
                solid_tri_infos.append(None)
                continue

        for c, n in global_add:
            global_skin_colors[c] += n
        solid_tri_infos.append(payload)

    if global_skin_colors:
        global_dominant = list(global_skin_colors.most_common(1)[0][0])
    else:
        # No surface triangles found — use skin color at part center as fallback
        gx, gy, gz = grid[0] // 2, grid[1] // 2, grid[2] // 2
        rgba = skin.get_face_color(part, "inner", "front", gx, gy, gz, part_dims, **sample_kw)
        global_dominant = [round(int(rgba[0])/255, 4), round(int(rgba[1])/255, 4), round(int(rgba[2])/255, 4)]

    # ─── Pass 2: assign final colors ───
    result_colors = []
    tri_rgb_arrays = []       # per solid, aligned with solid_tri_infos
    for si, info in enumerate(solid_tri_infos):
        if info is None:
            result_colors.append(None)
            tri_rgb_arrays.append(None)
            continue
        color_weights, n_tris = info[-2], info[-1]
        solid_dominant = list(max(color_weights, key=color_weights.get)) if color_weights else global_dominant

        if info[0] == "vec":
            textured, tri_rgb_q = info[1], info[2]
            if mode == "body":
                tri_rgb = np.tile(np.asarray(solid_dominant, dtype=np.float64), (n_tris, 1))
            else:
                # Triangles not on the part's surface (interior cuts, chamfers on
                # connectors…) have no skin pixel — fall back to this solid's own
                # dominant surface colour, not the part-wide one. The global dominant is
                # the torso/leg bulk colour, which looks wrong on a hip connector that
                # should match its local neighbourhood.
                tri_rgb = np.where(textured[:, None], tri_rgb_q,
                                   np.asarray(solid_dominant, dtype=np.float64))
            result_colors.append(tri_rgb.tolist())
            tri_rgb_arrays.append(tri_rgb)
        else:
            tri_info = info[1]
            if mode == "body":
                tri_colors = [solid_dominant] * n_tris
            else:
                # Same fallback as above, scalar form.
                tri_colors = [c if c else solid_dominant for c in tri_info]
            result_colors.append(tri_colors)
            tri_rgb_arrays.append(None)

    # ─── Build flat arrays + per-solid output ───
    all_positions, all_colors, all_normals = [], [], []
    solids_out = []
    kept = 0
    for si, s in enumerate(solids):
        info = solid_tri_infos[si]
        if info is None:
            continue
        n_tris = info[-1]
        if not n_tris:
            continue
        positions = s.get("positions", [])
        sol_positions = positions[:n_tris * 9]                      # copy — never share cache lists
        if info[0] == "vec":
            nv = info[3]
            sol_normals = np.repeat(nv, 3, axis=0).ravel().tolist()  # first-vertex normal × 3 verts
            sol_colors = np.repeat(tri_rgb_arrays[si], 3, axis=0).ravel().tolist()
        else:
            normals = s.get("normals", [])
            tri_colors = result_colors[si]
            sol_normals, sol_colors = [], []
            for t in range(n_tris):
                pi = t * 9
                sol_normals += normals[pi:pi + 3] * 3               # first-vertex normal × 3 verts
                sol_colors += tri_colors[t] * 3
        all_positions.extend(sol_positions)
        all_normals.extend(sol_normals)
        all_colors.extend(sol_colors)
        solids_out.append({
            "positions": sol_positions,
            "normals": sol_normals,
            "colors": sol_colors,
            "source_file": s.get("source_file", f"solid_{si}"),
            "solid_id": s.get("id", si),
            **({"texture_faces": texture_faces[si]} if include_texture_faces else {}),
        })
        kept += 1

    # Quantize + sync per-solid colors (unless caller handles quantization)
    palette = []
    if not skip_quantize:
        all_colors, palette, _indices = quantize_colors(all_colors, max_colors)

        # Re-sync result_colors and solids_out with quantized colors: each
        # triangle takes its first vertex's color from the remapped flat array.
        tri_first = np.asarray(all_colors, dtype=np.float64).reshape(-1, 9)[:, :3]
        flat_offset = 0
        sol_idx = 0
        for si, info in enumerate(solid_tri_infos):
            if info is None:
                continue
            n_tris = info[-1]
            if not n_tris:
                continue
            result_colors[si] = tri_first[flat_offset:flat_offset + n_tris].tolist()
            solids_out[sol_idx]["colors"] = all_colors[flat_offset * 9:(flat_offset + n_tris) * 9]
            flat_offset += n_tris
            sol_idx += 1

    return {
        "colors": result_colors,
        "delete_indices": delete_indices,
        "palette": palette,
        "mode": mode,
        "positions": all_positions,
        "normals": all_normals,
        "colors_flat": all_colors,
        "solids_out": solids_out,
        "triangle_count": len(all_positions) // 9,
        "vertex_count": len(all_positions) // 3,
        "kept_solids": kept,
        "deleted_solids": len(delete_indices),
    }
