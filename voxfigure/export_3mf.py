"""3MF export compatible with BambuStudio.

Each STEP file → separate object in 3D/Objects/. Per-triangle coloring via
paint_color attribute. Matches BambuStudio's native import format.
"""

import os
import math
import zipfile
import json
import tempfile
import re
import numpy as np
from collections import Counter
from datetime import datetime
from .part_config import PART_DEFS


def _encode_paint_color(extruder_1based):
    """Encode extruder (1-based) to BambuStudio paint_color string."""
    state = extruder_1based
    bits = [False, False]  # split_sides = 0
    if state < 3:
        bits.append(bool(state & 1))
        bits.append(bool(state & 2))
    else:
        bits.extend([True, True])
        n = state - 3
        while n >= 15:
            bits.extend([True, True, True, True])
            n -= 15
        for i in range(4):
            bits.append(bool(n & (1 << i)))
    while len(bits) % 4 != 0:
        bits.append(False)
    result = ''
    for offset in range(0, len(bits), 4):
        code = 0
        for i in range(3, -1, -1):
            code = (code << 1) | int(bits[offset + i])
        result = (chr(code + 48) if code < 10 else chr(code + 55)) + result
    return result


def _dedup_vertices(positions, precision=2):
    """Deduplicate vertices via np.unique.

    Returns (unique_verts, tri_indices, valid) where `valid` indexes the
    surviving (non-degenerate) triangles in original order — apply it to any
    per-triangle parallel array (e.g. extruders).

    Zero-area triangles are dropped — BambuStudio's mesh processing crashes
    (core dump) on them. Two cases, both caused by the 2dp vertex rounding
    collapsing thin tessellation slivers:
      * two vertices round to the same point → equal indices;
      * three distinct points end up collinear → distinct indices, still
        zero area. The cross-product test catches both.
    """
    rounded = np.round(np.array(positions, dtype=np.float64).reshape(-1, 3), precision)
    unique_verts, inverse = np.unique(rounded, axis=0, return_inverse=True)
    tri_indices = inverse.reshape(-1, 3)
    v0 = unique_verts[tri_indices[:, 0]]
    v1 = unique_verts[tri_indices[:, 1]]
    v2 = unique_verts[tri_indices[:, 2]]
    cross = np.cross(v1 - v0, v2 - v0)
    area2 = np.linalg.norm(cross, axis=1)  # = 2 * triangle area
    valid = np.nonzero(area2 > 1e-9)[0]
    return unique_verts, tri_indices[valid], valid


def _group_solids_by_file(solids_list, tri_extruders_global):
    """Group solids by source_file. Returns dict: filename → {positions, tri_extruders}.

    Generated artifacts may keep STEP coordinates at the 2.5mm base size and
    attach ``position_scale`` to each solid. Deferring that multiplication to
    export avoids retaining a second full-model Python-float graph merely to
    preview a non-default pixel size. Unscaled solids have no marker and keep
    the original 1:1 behaviour.
    """
    groups = {}
    global_tri_offset = 0

    for sol in solids_list:
        fname = sol.get("source_file", "model")
        pos = sol.get("positions", [])
        n_tris = len(pos) // 9
        # Use per-solid tri_extruders if available, else slice from global
        sol_ext = sol.get("tri_extruders")
        if not sol_ext and tri_extruders_global:
            sol_ext = tri_extruders_global[global_tri_offset:global_tri_offset + n_tris]
        elif not sol_ext:
            sol_ext = [1] * n_tris

        if fname not in groups:
            groups[fname] = {"positions": [], "tri_extruders": []}
        try:
            position_scale = float(sol.get("position_scale", 1.0))
        except (TypeError, ValueError):
            position_scale = 1.0
        if abs(position_scale - 1.0) > 1e-9:
            groups[fname]["positions"].extend(v * position_scale for v in pos)
        else:
            groups[fname]["positions"].extend(pos)
        start = len(groups[fname]["tri_extruders"])
        groups[fname]["tri_extruders"].extend(sol_ext)
        global_tri_offset += n_tris

    return groups









# ─── Plate layout ─────────────────────────────────────────────────────────
# Every STEP file becomes one 3MF object. We default to a multi-plate project:
# one plate per anatomical part (head / body / each arm / each leg, from the
# source_file path), with that part's objects laid out on the plate. Plates tile
# in the global XY space exactly the way BambuStudio arranges them
# (PartPlate.cpp: origin = (col, -row) * bed_dim * (1 + 1/5)), so each part's
# objects land on their own plate's bed.
LAYOUT_GAP_MM = 5.0    # gap between objects within a plate's grid
_PLATE_GAP_FACTOR = 1.0 / 5.0  # BambuStudio's LOGICAL_PART_PLATE_GAP
_PART_ORDER = {p: i for i, p in enumerate(PART_DEFS)}  # plate order = part order
_PART_SYNONYMS = {"chest": "body", "waist": "body", "crotch": "body"}
# Safety lift so nothing peeks below z=0 in BambuStudio. With the 2dp bbox/vertex
# precision now aligned this should be 0, but kept as a knob in case something else
# (template origin offset, hidden transform, …) is still dragging parts below.
_BED_LIFT_MM = 1.0


def _part_of(source_file):
    """Anatomical part for a source_file ('head/foo.stp' or 'chest_for_print.stp')."""
    if "/" in source_file:
        return source_file.split("/", 1)[0]
    s = source_file.lower()
    for p in ("right_arm", "left_arm", "right_leg", "left_leg", "head", "body"):
        if p in s:
            return p
    for kw, p in _PART_SYNONYMS.items():
        if kw in s:
            return p
    return source_file  # unknown → its own plate


def _bed_size(project):
    """(width, height, cx, cy) in mm from a project's 'printable_area' polygon;
    falls back to a 256x256 bed centred at (128, 128)."""
    pts = []
    for s in (project.get("printable_area") if isinstance(project, dict) else None) or []:
        try:
            x, y = str(s).lower().split("x")
            pts.append((float(x), float(y)))
        except (ValueError, AttributeError):
            pass
    if len(pts) < 2:
        return (256.0, 256.0, 128.0, 128.0)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (max(xs) - min(xs), max(ys) - min(ys),
            (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def _bbox_xy(positions, precision=2):
    # Round to the same precision as _dedup_vertices / the vertex writer — otherwise
    # the bbox we use for layout (and the -mnz Z-lift) is at 0.001mm precision while
    # the actual 3MF vertices land on a 0.01mm grid, leaving room for sub-pixel
    # below-bed clipping when BambuStudio adds them.
    if len(positions) < 9:
        return (0.0, 0.0, 0.0, 0.0, 0.0)
    a = np.round(np.array(positions, dtype=np.float64).reshape(-1, 3), precision)
    mn, mx = a.min(axis=0), a.max(axis=0)
    return (float(mn[0]), float(mn[1]), float(mn[2]), float(mx[0] - mn[0]), float(mx[1] - mn[1]))


def _pack_pages(fnames, bbox, bed_w, bed_h):
    """Shelf-pack (next-fit, decreasing height) fnames into pages that each fit
    the bed. Returns a list of pages; each page is {fname: (px, py)} = where the
    object's (min_x, min_y) corner goes in a (0,0)-(bed_w, bed_h) frame, with the
    packed block centred on the bed."""
    g = LAYOUT_GAP_MM
    objs = sorted(fnames, key=lambda f: -bbox[f][4])  # tallest first
    pages_raw = []                       # each: list of (fname, lx, ly_top, w, h); page-y grows down from 0
    cur, sx, sy, sh = [], 0.0, 0.0, 0.0  # current page, shelf used-width, shelf top-y, shelf height
    for f in objs:
        w, h = bbox[f][3], bbox[f][4]
        if not cur:                          # first object on a fresh page
            sx, sy, sh = 0.0, 0.0, h
        elif sx + g + w > bed_w:             # doesn't fit current shelf → start the next one
            ny = sy + sh + g
            if ny + h > bed_h:               # next shelf would overflow the bed → start the next page
                pages_raw.append(cur)
                cur, ny = [], 0.0
            sx, sy, sh = 0.0, ny, h
        x = sx + (g if sx else 0.0)          # no leading gap at the start of a shelf (sx == 0)
        cur.append((f, x, sy, w, h))
        sx = x + w
        sh = max(sh, h)
    if cur:
        pages_raw.append(cur)

    pages = []
    for page in pages_raw:
        maxx = max(lx + w for _f, lx, _ly, w, _h in page)
        maxy = max(ly + h for _f, _lx, ly, _w, h in page)
        ox = (bed_w - maxx) / 2.0
        oy = (bed_h - maxy) / 2.0
        # page-y grows down; bed-y grows up — flip when centring on the bed
        pages.append({f: (ox + lx, oy + maxy - ly - h) for f, lx, ly, w, h in page})
    return pages




def _plate_layout(file_groups, bed, bed_lift=_BED_LIFT_MM, flat_sources=None,
                  layout_mode="plates", vertex_precision=2):
    """Export ordinary body parts as a multi-plate print project."""
    bw, bh, bcx, bcy = bed
    flat_sources = flat_sources or set()    # source_files that must sit flat on z=0 (bed_lift=0)
    bbox = {fn: _bbox_xy(g.get("positions") or [], vertex_precision) for fn, g in file_groups.items()}

    parts = {}
    for fn in file_groups:
        parts.setdefault(_part_of(fn), []).append(fn)
    ordered_parts = sorted(parts, key=lambda p: (_PART_ORDER.get(p, len(_PART_ORDER)), p))

    plate_units = []  # list of (display_name, {fname: (px, py)})
    for p in ordered_parts:
        base = p.replace("_", " ").title()
        margin = 0.0
        pages = _pack_pages(parts[p], bbox, bw, bh)
        for j, page in enumerate(pages):
            if margin:
                page = {fn: (x + margin, y + margin) for fn, (x, y) in page.items()}
            plate_units.append((base if j == 0 else f"{base} {j + 1}", page))

    cols = max(1, math.ceil(math.sqrt(len(plate_units))))  # = BambuStudio compute_colum_count
    stride_x, stride_y = bw * (1 + _PLATE_GAP_FACTOR), bh * (1 + _PLATE_GAP_FACTOR)
    bl_x0, bl_y0 = bcx - bw / 2.0, bcy - bh / 2.0          # bed bottom-left corner (0,0 for our templates)

    ordered, offsets, plate_of, plate_names = [], {}, {}, {}
    for k, (name, page) in enumerate(plate_units):         # k = 0-based plate index
        plate_bl_x = (k % cols) * stride_x + bl_x0
        plate_bl_y = -(k // cols) * stride_y + bl_y0
        for fn, (px, py) in page.items():
            mnx, mny, mnz, _w, _h = bbox[fn]
            lift = 0.0 if fn in flat_sources else bed_lift
            offsets[fn] = (plate_bl_x + px - mnx, plate_bl_y + py - mny, -mnz + lift)
            plate_of[fn] = k + 1
            ordered.append(fn)
        plate_names[k + 1] = name
    return ordered, offsets, plate_of, plate_names


_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "printer_templates")


def _list_template_files():
    """Return sorted list of template JSON filenames, or [] if dir missing."""
    if not os.path.isdir(_TEMPLATES_DIR):
        return []
    return sorted(f for f in os.listdir(_TEMPLATES_DIR) if f.endswith(".json"))


def _resolve_template_path(printer_template):
    """Return path to chosen template (or first available), or None."""
    if printer_template:
        return os.path.join(_TEMPLATES_DIR, f"{printer_template}.json")
    files = _list_template_files()
    return os.path.join(_TEMPLATES_DIR, files[0]) if files else None


def list_printer_templates():
    """Return [{id, name}, ...] of available printer templates."""
    out = []
    for f in _list_template_files():
        tid = f[:-5]
        try:
            with open(os.path.join(_TEMPLATES_DIR, f)) as fp:
                name = json.load(fp).get("printer_settings_id") or tid
        except Exception:
            name = tid
        out.append({"id": tid, "name": name})
    return out


# ─── 3MF package scaffolding ───
# package format for ordinary-body multi-plate projects.

_CONTENT_TYPES_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
    ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
    ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
    ' <Default Extension="png" ContentType="image/png"/>\n'
    ' <Default Extension="gcode" ContentType="text/x.gcode"/>\n'
    '</Types>')

_ROOT_RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
    ' <Relationship Target="/3D/3dmodel.model" Id="rel-1" '
    'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
    '</Relationships>')

_SLICE_INFO_CONFIG = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<config>\n'
    '  <header>\n'
    '    <header_item key="X-BBL-Client-Type" value="slicer"/>\n'
    '    <header_item key="X-BBL-Client-Version" value="02.05.02.51"/>\n'
    '  </header>\n'
    '</config>')


def _model_metadata_lines():
    """The 3 <metadata> header lines (Application / 3mfVersion / CreationDate) that
    open both writers' 3D/3dmodel.model assembly."""
    return [
        ' <metadata name="Application">BambuStudio-02.05.02.51</metadata>\n',
        ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n',
        f' <metadata name="CreationDate">{datetime.now().strftime("%Y-%m-%d")}</metadata>\n',
    ]


def _cut_information_xml(object_ids):
    """Metadata/cut_information.xml — one <object> per id (the per-file mesh ids
    for the production writer, the single assembly id for the multi-part writer)."""
    lines = ['<?xml version="1.0" encoding="utf-8"?>\n', '<objects>\n']
    for oid in object_ids:
        lines.append(f' <object id="{oid}">\n')
        lines.append(f'  <cut_id id="0" check_sum="1" connectors_cnt="0"/>\n')
        lines.append(f' </object>\n')
    lines.append('</objects>')
    return ''.join(lines)


def _filament_sequence_json(num_plates):
    return json.dumps({f"plate_{p}": {"sequence": []} for p in range(1, num_plates + 1)})


def _resize_project_settings(project, num_extruders, color_hexes):
    """In-place resize a BambuStudio project_settings template's per-filament arrays
    to num_extruders, set the filament colours + MMU flags. Returns the mutated
    project. Shared verbatim by both 3MF writers."""
    _skip_prefixes = ('extruder_', 'machine_', 'head_wrap')
    _skip_keys = {
        'bed_exclude_area', 'post_process', 'flush_volumes_matrix',
        'first_layer_print_sequence', 'other_layers_print_sequence',
        'different_settings_to_system', 'inherits_group',
        'default_filament_colour', 'default_filament_profile',
    }
    # Templates mix per-filament arrays of different base sizes (e.g. 4 and 8);
    # collect all sizes seen on filament_* arrays, then resize anything matching.
    per_filament_lens = {
        len(v) for k, v in project.items()
        if k.startswith('filament_') and isinstance(v, list) and v
    }
    for key, value in project.items():
        if not isinstance(value, list) or len(value) == 0:
            continue
        if key in _skip_keys or any(key.startswith(p) for p in _skip_prefixes):
            continue
        if key.startswith('filament_') or len(value) in per_filament_lens:
            if len(value) != num_extruders:
                project[key] = [value[0] if value else '0'] * num_extruders
    for key in ('different_settings_to_system', 'inherits_group'):
        old = project.get(key, [''])
        project[key] = [old[0] if old else ''] + [''] * num_extruders + [old[-1] if len(old) > 1 else '']
    project['default_filament_colour'] = [''] * num_extruders
    project['default_filament_profile'] = [project.get('default_filament_profile', [''])[0] or ''] * num_extruders
    project['flush_volumes_matrix'] = ['0'] * (num_extruders * num_extruders * 2)
    project['filament_colour'] = color_hexes
    project['single_extruder_multi_material'] = '1'
    project['enable_prime_tower'] = '1'
    for k in ['solid_infill_filament', 'sparse_infill_filament', 'wall_filament']:
        if k in project and (project[k] == 0 or project[k] == '0'):
            project[k] = '1'
    return project


def export_step_mesh_3mf(mesh_data: dict, output_path: str, printer_template: str = None,
                         bed_lift: float = _BED_LIFT_MM, flat_sources=None,
                         layout_mode: str = "plates", vertex_precision: int = 2):
    """Export ordinary body parts as a multi-plate print project."""
    if vertex_precision not in (2, 3, 4, 5, 6):
        raise ValueError("Unsupported mesh vertex precision")
    transform_precision = max(4, vertex_precision)
    palette = mesh_data.get("palette", [])
    solids_list = mesh_data.get("solids")
    tri_extruders_global = mesh_data.get("tri_extruders")

    if layout_mode != "plates":
        raise ValueError("Only part-by-part print projects are supported")
    flat_sources = set(flat_sources or ())

    # Group by source file
    if solids_list:
        file_groups = _group_solids_by_file(solids_list, tri_extruders_global)
    else:
        all_pos = list(mesh_data.get("positions", []))
        n_tris = len(all_pos) // 9
        ext = tri_extruders_global if tri_extruders_global else [1] * n_tris
        file_groups = {"model": {"positions": all_pos, "tri_extruders": ext}}

    num_files = len(file_groups)
    if num_files == 0:
        return output_path

    num_extruders = len(palette) if palette else 1
    color_hexes = [f"#{c[0]:02X}{c[1]:02X}{c[2]:02X}" for c in palette] if palette else ["#808080"]

    # Pre-encode paint_color
    all_exts = set()
    for g in file_groups.values():
        all_exts.update(g["tri_extruders"])
    paint_cache = {ext: _encode_paint_color(ext) for ext in all_exts}

    # Printer template (also gives the bed size used by the plate layout)
    template_path = _resolve_template_path(printer_template)
    if template_path and os.path.exists(template_path):
        with open(template_path, 'r') as tf:
            project = json.load(tf)
    else:
        project = {}

    # Spread ordinary-body objects into per-part plates.
    file_list, obj_offsets, plate_of, plate_names = _plate_layout(
        file_groups, _bed_size(project), bed_lift=bed_lift,
        flat_sources=flat_sources, layout_mode=layout_mode,
        vertex_precision=vertex_precision)
    num_plates = len(plate_names)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Write to a temp file and atomically rename, so an interrupted export never
    # leaves a half-written (corrupt) 3MF where the previous good one was.
    tmp_path = output_path + ".part"
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # [Content_Types].xml + _rels/.rels (shared scaffolding)
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
        zf.writestr("_rels/.rels", _ROOT_RELS_XML)

        # ID scheme (matches BambuStudio):
        # object_N.model has mesh object id = 2*N-1 (odd: 1, 3, 5, ...)
        # assembly wrapper object id = 2*N (even: 2, 4, 6, ...)
        mesh_ids = [2 * i + 1 for i in range(num_files)]   # 1, 3, 5, ...
        asm_ids = [2 * i + 2 for i in range(num_files)]     # 2, 4, 6, ...

        # 3D/_rels/3dmodel.model.rels — reference all object files
        rels_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        ]
        for i in range(num_files):
            rels_lines.append(
                f' <Relationship Target="/3D/Objects/object_{i+1}.model" Id="rel-{i+1}" '
                f'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
            )
        rels_lines.append('</Relationships>')
        zf.writestr("3D/_rels/3dmodel.model.rels", ''.join(rels_lines))

        # 3D/3dmodel.model — assembly with one wrapper per file
        asm_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>\n',
            '<model unit="millimeter" xml:lang="en-US" '
            'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
            'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
            'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
            'requiredextensions="p">\n',
            *_model_metadata_lines(),
            ' <resources>\n',
        ]
        for i in range(num_files):
            asm_lines.append(f'  <object id="{asm_ids[i]}" type="model">\n')
            asm_lines.append(f'   <components>\n')
            asm_lines.append(
                f'    <component p:path="/3D/Objects/object_{i+1}.model" '
                f'objectid="{mesh_ids[i]}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
            )
            asm_lines.append(f'   </components>\n')
            asm_lines.append(f'  </object>\n')
        asm_lines.append(' </resources>\n')
        asm_lines.append(' <build>\n')
        for i in range(num_files):
            tx, ty, tz = obj_offsets[file_list[i]]
            asm_lines.append(
                f'  <item objectid="{asm_ids[i]}" '
                f'transform="1 0 0 0 1 0 0 0 1 {tx:.{transform_precision}f} {ty:.{transform_precision}f} {tz:.{transform_precision}f}" '
                f'printable="1"/>\n'
            )
        asm_lines.append(' </build>\n')
        asm_lines.append('</model>\n')
        zf.writestr("3D/3dmodel.model", ''.join(asm_lines))

        # 3D/Objects/object_N.model — one per STEP file
        CHUNK = 5000
        # Cache per-file stats so the config section doesn't recompute them
        file_stats = {}  # fname → (n_tris_g, base_ext)
        for idx, fname in enumerate(file_list):
            group = file_groups[fname]
            positions = group["positions"]
            tri_ext = group["tri_extruders"]

            unique_verts, tri_indices, valid = _dedup_vertices(positions, vertex_precision)
            if len(valid) != len(tri_ext):
                tri_ext = [tri_ext[t] for t in valid]
            n_tris_g = len(tri_indices)

            # Base extruder for this object
            ext_counts = Counter(tri_ext)
            base_ext = ext_counts.most_common(1)[0][0] if ext_counts else 1
            file_stats[fname] = (n_tris_g, base_ext)

            zi = zipfile.ZipInfo(f'3D/Objects/object_{idx+1}.model')
            zi.compress_type = zipfile.ZIP_DEFLATED
            with zf.open(zi, 'w', force_zip64=True) as raw:
                raw.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
                raw.write(b'<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
                           b'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
                           b'unit="millimeter" xml:lang="en-US" requiredextensions="p">\n')
                raw.write(b' <resources>\n')
                raw.write(f'  <object id="{mesh_ids[idx]}" type="model">\n'.encode())
                raw.write(b'   <mesh>\n    <vertices>\n')

                for i in range(0, len(unique_verts), CHUNK):
                    chunk = unique_verts[i:i+CHUNK]
                    lines = ''.join(f'     <vertex x="{x:.{vertex_precision}f}" y="{y:.{vertex_precision}f}" z="{z:.{vertex_precision}f}"/>\n'
                                    for x, y, z in chunk)
                    raw.write(lines.encode())

                raw.write(b'    </vertices>\n    <triangles>\n')

                for i in range(0, n_tris_g, CHUNK):
                    lines = []
                    for t in range(i, min(i + CHUNK, n_tris_g)):
                        v1, v2, v3 = tri_indices[t]
                        ext = tri_ext[t]
                        if ext != base_ext:
                            lines.append(f'     <triangle v1="{v1}" v2="{v2}" v3="{v3}" paint_color="{paint_cache[ext]}"/>\n')
                        else:
                            lines.append(f'     <triangle v1="{v1}" v2="{v2}" v3="{v3}"/>\n')
                    raw.write(''.join(lines).encode())

                raw.write(b'    </triangles>\n   </mesh>\n  </object>\n')
                raw.write(b' </resources>\n <build/>\n</model>\n')

        # Metadata/model_settings.config
        settings_lines = ['<?xml version="1.0" encoding="UTF-8"?>\n', '<config>\n']
        for i, fname in enumerate(file_list):
            n_tris_g, base_ext = file_stats[fname]
            settings_lines.append(f'  <object id="{asm_ids[i]}">\n')
            settings_lines.append(f'    <metadata key="name" value="{fname}"/>\n')
            settings_lines.append(f'    <metadata key="extruder" value="{base_ext}"/>\n')
            settings_lines.append(f'    <metadata face_count="{n_tris_g}"/>\n')
            settings_lines.append(f'    <part id="{mesh_ids[i]}" subtype="normal_part">\n')
            settings_lines.append(f'      <metadata key="name" value="{fname}"/>\n')
            settings_lines.append(f'      <metadata key="source_file" value="{fname}"/>\n')
            settings_lines.append(f'    </part>\n')
            settings_lines.append(f'  </object>\n')
        plate_idxs = {}  # plater_id -> [object index in file_list]
        for i in range(num_files):
            plate_idxs.setdefault(plate_of[file_list[i]], []).append(i)
        for pid in sorted(plate_idxs):
            settings_lines.append('  <plate>\n')
            settings_lines.append(f'    <metadata key="plater_id" value="{pid}"/>\n')
            settings_lines.append(f'    <metadata key="plater_name" value="{plate_names.get(pid, "")}"/>\n')
            settings_lines.append('    <metadata key="locked" value="false"/>\n')
            settings_lines.append('    <metadata key="filament_map_mode" value="Auto For Flush"/>\n')
            for i in plate_idxs[pid]:
                settings_lines.append(f'    <model_instance>\n')
                settings_lines.append(f'      <metadata key="object_id" value="{asm_ids[i]}"/>\n')
                settings_lines.append(f'      <metadata key="instance_id" value="0"/>\n')
                settings_lines.append(f'      <metadata key="identify_id" value="{i+1}"/>\n')
                settings_lines.append(f'    </model_instance>\n')
            settings_lines.append('  </plate>\n')
        settings_lines.append('  <assemble>\n')
        for i in range(num_files):
            tx, ty, tz = obj_offsets[file_list[i]]
            settings_lines.append(
                f'   <assemble_item object_id="{asm_ids[i]}" instance_id="0" '
                f'transform="1 0 0 0 1 0 0 0 1 {tx:.{transform_precision}f} {ty:.{transform_precision}f} {tz:.{transform_precision}f}" offset="0 0 0" />\n'
            )
        settings_lines.append('  </assemble>\n')
        settings_lines.append('</config>')
        zf.writestr("Metadata/model_settings.config", ''.join(settings_lines))

        # Metadata/project_settings.config (template was loaded above for the bed size)
        _resize_project_settings(project, num_extruders, color_hexes)
        zf.writestr("Metadata/project_settings.config", json.dumps(project, indent=2))

        zf.writestr("Metadata/slice_info.config", _SLICE_INFO_CONFIG)
        zf.writestr("Metadata/cut_information.xml", _cut_information_xml(mesh_ids))
        zf.writestr("Metadata/filament_sequence.json", _filament_sequence_json(num_plates))

    os.replace(tmp_path, output_path)
    return output_path

