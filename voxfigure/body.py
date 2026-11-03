"""Shared skin → preview/print pipeline for ordinary Steve and Alex only."""
import base64
from collections import defaultdict, Counter
import json
import math
from pathlib import Path
import numpy as np
from . import geometry
from .skin_parser import SkinParser
from .step_colorizer import color_solids, quantize_color_indices
from .part_config import BASE_PIXEL_SIZE
from .export_3mf import export_step_mesh_3mf

def generate(skin_path, model, pixel_size, max_colors):
    skin = SkinParser(str(skin_path), model)
    parts = defaultdict(lambda: {'single': [], 'multi': []})
    for part, single, solids in geometry.load_geometry(model):
        parts[part]['single' if single else 'multi'].extend(solids)
    output = []
    for part, groups in parts.items():
        for s in groups['single']:
            output.append(dict(positions=s['positions'], colors=[.53] * len(s['positions']), source_file=s['source_file']))
        if groups['multi']:
            result = color_solids(groups['multi'], skin, BASE_PIXEL_SIZE, part, model,
                                  mode='face', max_colors=max_colors, skip_quantize=True)
            output.extend(result['solids_out'])
    if not output:
        raise ValueError('No model geometry was generated')
    colors = [v for s in output for v in s['colors']]
    palette, indices = quantize_color_indices(colors, max_colors)
    triangle_colors = (np.asarray(indices)[::3] + 1).tolist()
    offset = 0
    for s in output:
        count = len(s['positions']) // 9
        s['tri_extruders'] = triangle_colors[offset:offset + count]
        s['position_scale'] = pixel_size / BASE_PIXEL_SIZE
        s.pop('colors', None); s.pop('normals', None)
        offset += count
    return {'solids': output, 'palette': palette, 'model': model, 'pixel_size': pixel_size}

def preview(mesh):
    positions, colors, parts = [], [], []
    offset = 0
    for s in mesh['solids']:
        positions.extend(v * s['position_scale'] for v in s['positions'])
        for extruder in s['tri_extruders']:
            colors.extend([extruder - 1] * 3)
        count = len(s['positions']) // 3
        parts.append({'start': offset, 'count': count, 'part': s['source_file'].split('/')[0]})
        offset += count
    pos = np.asarray(positions, dtype='<f4').reshape(-1, 3)
    return {'positions': base64.b64encode(pos.tobytes()).decode(),
            'colors': base64.b64encode(np.asarray(colors, dtype=np.uint8).tobytes()).decode(),
            'palette': mesh['palette'], 'parts': parts, 'triangles': len(colors) // 3,
            'height_mm': round(float(np.ptp(pos[:, 2])), 2)}

def joint_pins(pixel_size, model):
    scale = pixel_size / 4
    arm = 14 if model == 'steve' else 10
    groups = {'left_arm': (arm, arm), 'right_arm': (arm, arm),
              'left_leg': (13.9, 13.9), 'right_leg': (13.9, 13.9), 'body': (14, 14, 23.5)}
    radius = 1.4 * scale
    for part, lengths in groups.items():
        for number, length in enumerate(lengths, 1):
            height = length * scale; triangles = []
            for i in range(64):
                a, b = [2 * math.pi * j / 64 for j in (i, i + 1)]
                p = [radius + radius * math.cos(a), radius + radius * math.sin(a), 0]
                q = [radius + radius * math.cos(b), radius + radius * math.sin(b), 0]
                P, Q = [*p[:2], height], [*q[:2], height]
                triangles.extend([p, q, Q, p, Q, P, [radius, radius, 0], q, p, [radius, radius, height], P, Q])
            yield {'positions': np.array(triangles).ravel().tolist(), 'tri_extruders': [1] * 256,
                   'source_file': f'joint_rods/{part}_{number}'}

def export(mesh, path, printer):
    # Keep the same body/chest variant and joint pins as the full ordinary kit.
    solids = list(mesh['solids'])
    mapping = json.loads(Path(__file__).with_name('chest_mapping.json').read_text())
    original = {s['solid_id']: s for s in solids if s.get('solid_id') is not None
                and s['source_file'].endswith('/chest_mutile_color.stp')}
    flat = geometry.print_chest(mesh['model'])
    for item in mapping:
        normal = original.get(item['normal'])
        if normal is None:
            continue  # a transparent outer skin solid may have been removed
        s = flat[item['forprint']]; count = len(s['positions']) // 9
        colors = normal['tri_extruders']
        transferred = colors if len(colors) == count else [Counter(colors).most_common(1)[0][0]] * count
        solids.append({'positions': s['positions'], 'position_scale': mesh['pixel_size'] / BASE_PIXEL_SIZE,
                       'tri_extruders': transferred, 'source_file': 'chest_mutile_color_for_print.stp'})
    pins = list(joint_pins(mesh['pixel_size'], mesh['model']))
    export_step_mesh_3mf({'solids': solids + pins, 'palette': mesh['palette']}, str(path), printer,
                         flat_sources={s['source_file'] for s in pins})
