"""Fixed ordinary-body sources; no user-supplied CAD paths or developer endpoints."""
from functools import lru_cache
from pathlib import Path
import gzip
import hashlib
import json
import os
import threading
import numpy as np
from .part_config import BASE_PIXEL_SIZE, get_part_config

ASSETS = Path(__file__).resolve().parent.parent / 'assets'
CACHE = Path(os.environ.get('VOXFIGURE_CACHE', str(ASSETS.parent / '.cache')))
_lock = threading.RLock()

def tessellate(path, part, model):
    # Import only when generating. The home page/options do not need OCP startup.
    from .step_tessellator import tessellate_step
    return tessellate_step(str(path), BASE_PIXEL_SIZE, part, model)

def mirror_y(solid):
    out = dict(solid)
    for key in ('positions', 'normals'):
        a = np.array(solid[key]).reshape(-1, 3, 3)
        a[:, :, 1] *= -1
        out[key] = a[:, [0, 2, 1], :].ravel().tolist()
    out['center'] = [solid['center'][0], -solid['center'][1], solid['center'][2]]
    lo, hi = solid['bbox_min'], solid['bbox_max']
    out['bbox_min'] = [lo[0], -hi[1], lo[2]]
    out['bbox_max'] = [hi[0], -lo[1], hi[2]]
    return out

def _source_files(model):
    if model not in ('steve', 'alex'):
        raise ValueError('Unsupported model')
    return sorted((ASSETS / model).rglob('*.stp'))

@lru_cache(maxsize=2)
def load_geometry(model):
    paths = _source_files(model)
    if not paths:
        raise RuntimeError('Body assets are missing')
    digest = hashlib.sha256(b'ordinary-body-cache-v1')
    for path in paths:
        digest.update(path.relative_to(ASSETS).as_posix().encode())
        digest.update(path.read_bytes())
    cache_file = CACHE / (model + '-' + digest.hexdigest()[:20] + '.json.gz')
    with _lock:
        if cache_file.exists():
            try:
                with gzip.open(cache_file, 'rt', encoding='utf-8') as f:
                    return json.load(f)
            except (ValueError, OSError, EOFError):
                pass
        groups = []
        for path in paths:
            relative = path.relative_to(ASSETS / model)
            if len(relative.parts) != 3 or relative.parts[1] not in ('mutile_color', 'single_color'):
                continue
            part, kind, name = relative.parts
            single = kind == 'single_color'
            if single and (path.parent.parent / 'mutile_color' / name).exists():
                continue
            raw = tessellate(path, part, model)
            for actual in (part, {'right_arm': 'left_arm', 'right_leg': 'left_leg'}.get(part)):
                if actual is None:
                    continue
                solids = [mirror_y(s) if actual != part else dict(s) for s in raw]
                config = get_part_config(actual, model, BASE_PIXEL_SIZE)
                for s in solids:
                    lo, hi = np.array(s['bbox_min']), np.array(s['bbox_max'])
                    outside = np.any(lo < np.array(config['inner_box_min']) - .05) or np.any(hi > np.array(config['inner_box_max']) + .05)
                    s['layer'] = 'outer' if outside else 'inner'
                    s['source_file'] = actual + '/' + name
                groups.append((actual, single, solids))
        if set(g[0] for g in groups) != {'head', 'body', 'left_arm', 'right_arm', 'left_leg', 'right_leg'}:
            raise RuntimeError('Incomplete ordinary-body assets')
        CACHE.mkdir(parents=True, exist_ok=True)
        temporary = cache_file.with_suffix('.tmp-' + str(os.getpid()))
        with gzip.open(temporary, 'wt', encoding='utf-8') as f:
            json.dump(groups, f, separators=(',', ':'))
        os.replace(temporary, cache_file)
        return groups

@lru_cache(maxsize=2)
def print_chest(model):
    _source_files(model)  # validate before resolving a path
    return tessellate(ASSETS / model / 'for_print_step/chest_mutile_color_for_print.stp', 'body', model)
