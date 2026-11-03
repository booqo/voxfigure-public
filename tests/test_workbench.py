from io import BytesIO
import base64
import importlib.util
import json
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
import numpy as np
import pytest
from PIL import Image
import app as web
from voxfigure import body, geometry
from voxfigure.part_config import get_part_config

ROOT = Path(__file__).resolve().parents[1]

def skin_bytes(size=(64, 64)):
    out = BytesIO(); Image.new('RGBA', size, (170, 65, 30, 255)).save(out, format='PNG')
    return out.getvalue()

def geometry_fixture(model):
    """Small synthetic surfaces, not a substitute for the native CAD test."""
    result = []
    for part in ('head', 'body', 'left_arm', 'right_arm', 'left_leg', 'right_leg'):
        cfg = get_part_config(part, model, 2.5)
        lo, hi = cfg['inner_box_min'], cfg['inner_box_max']
        positions = [hi[0], lo[1], lo[2], hi[0], hi[1], lo[2], hi[0], hi[1], hi[2]]
        source = part + ('/chest_mutile_color.stp' if part == 'body' else '/surface.stp')
        result.append((part, False, [dict(id=0, positions=positions, normals=[1., 0., 0.] * 3,
            layer='inner', center=[(a+b)/2 for a,b in zip(lo,hi)], bbox_min=lo, bbox_max=hi, source_file=source)]))
    return result

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(geometry, 'load_geometry', geometry_fixture)
    # Map all printable chest test triangles to the one colored body fixture.
    flat = [dict(positions=[0.,0.,0.,2.,0.,0.,0.,2.,0.]) for _ in range(10000)]
    monkeypatch.setattr(geometry, 'print_chest', lambda model: flat)
    web.app.config['TESTING'] = True
    return web.app.test_client()

def form(**values):
    return {'skin': (BytesIO(skin_bytes()), '皮肤.png'), 'model': 'steve',
            'pixel_size': '2.5', 'max_colors': '8', **values}

def test_documented_routes_and_unknown_paths(client):
    routes = {r.rule for r in web.app.url_map.iter_rules()}
    assert routes == {'/', '/api/options', '/api/generate', '/api/export', '/static/<path:filename>'}
    for path in ('/unknown-page', '/api/unknown-operation', '/api/generate/extra'):
        assert client.get(path).status_code == 404
    assert client.get('/').status_code == 200
    assert client.get('/api/options').json['models'] == ['steve', 'alex']

@pytest.mark.parametrize('values', [dict(model='unknown-model'), dict(model='other-model'), dict(pixel_size='nan'),
    dict(pixel_size='inf'), dict(pixel_size='0'), dict(max_colors='500'), dict(max_colors='2.5'),
    dict(printer='../../unknown'), dict(custom_option='value'), dict(path='../../outside')])
def test_invalid_or_unknown_parameters_are_rejected(client, values):
    assert client.post('/api/generate', data=form(**values)).status_code == 400

def test_bad_skin_and_cross_origin_rejected(client):
    assert client.post('/api/generate', data={'skin':(BytesIO(b'not png'),'fake.png')}).status_code == 400
    assert client.post('/api/generate', data={'skin':(BytesIO(skin_bytes((16,16))),'tiny.png')}).status_code == 400
    assert client.post('/api/generate', data=form(), headers={'Origin':'https://another.site'}).status_code == 403
    assert client.post('/api/generate', data={'skin':(BytesIO(b'0'*(2*1024*1024)),'large.png')}).status_code == 413

@pytest.mark.parametrize('model', ['steve', 'alex'])
def test_preview_scale_and_download_package(client, model):
    one = client.post('/api/generate', data=form(model=model)).json
    two = client.post('/api/generate', data=form(model=model, pixel_size='5')).json
    p = lambda d: np.frombuffer(base64.b64decode(d['positions']), dtype='<f4')
    np.testing.assert_allclose(p(two), p(one)*2)
    assert len(one['palette']) <= 8 and one['palette'] == two['palette']
    assert {r['part'] for r in one['parts']} == {'head','body','left_arm','right_arm','left_leg','right_leg'}
    assert {r['file'].split('/')[0] for r in one['parts']} == {r['part'] for r in one['parts']}
    np.testing.assert_allclose([r['center'] for r in two['parts']],
                               np.array([r['center'] for r in one['parts']])*2, atol=.11)
    response = client.post('/api/export', data=form(model=model))
    assert response.status_code == 200
    assert response.mimetype == 'model/3mf'
    with zipfile.ZipFile(BytesIO(response.data)) as archive:
        assembly = ET.fromstring(archive.read('3D/3dmodel.model'))
        assert assembly.attrib['unit'] == 'millimeter'
        config = archive.read('Metadata/model_settings.config').decode()
        assert 'joint_rods/' in config and 'chest_mutile_color_for_print.stp' in config
        assert 'right_arm/' in config and 'left_arm/' in config
        project = json.loads(archive.read('Metadata/project_settings.config'))
        assert project['filament_colour'] == ['#AA411E']
        objects = [n for n in archive.namelist() if n.startswith('3D/Objects/')]
        assert len(objects) >= 17
        for name in objects:
            ET.fromstring(archive.read(name))

def test_parallel_generation_reports_busy(client):
    with web._generation_lock:
        assert client.post('/api/generate', data=form()).status_code == 409

def test_mirror_preserves_source_and_winding():
    original = geometry_fixture('steve')[2][2][0]
    before = json.dumps(original)
    mirrored = geometry.mirror_y(original)
    assert json.dumps(original) == before
    p = np.array(mirrored['positions']).reshape(-1,3)
    assert np.dot(np.cross(p[1]-p[0],p[2]-p[0]), mirrored['normals'][:3]) >= 0
    assert mirrored['bbox_min'][1] == -original['bbox_max'][1]

def test_pin_dimensions_and_closed_triangle_edges():
    for model, arm_length in [('alex',10),('steve',14)]:
        pins = list(body.joint_pins(4, model))
        assert len(pins) == 11
        p = np.array(pins[0]['positions']).reshape(-1,3)
        np.testing.assert_allclose(np.ptp(p,axis=0), [2.8,2.8,arm_length])
        edges = {}
        for triangle in np.round(p,8).reshape(-1,3,3):
            for a,b in ((0,1),(1,2),(2,0)):
                key = tuple(sorted((tuple(triangle[a]),tuple(triangle[b]))))
                edges[key] = edges.get(key,0)+1
        assert set(edges.values()) == {2}

def test_release_assets_and_modules_are_allowlisted():
    assert {p.name for p in (ROOT/'assets').iterdir()} == {'steve','alex'}
    assert len(list((ROOT/'assets').rglob('*.stp'))) == 70
    expected = {
        'voxfigure': {
            '__init__.py', 'body.py', 'chest_mapping.json', 'color_quantizer.py',
            'detail_palette.py', 'export_3mf.py', 'geometry.py', 'part_config.py',
            'skin_parser.py', 'step_colorizer.py', 'step_tessellator.py',
            'printer_templates/bambu_A1_0.4.json', 'printer_templates/bambu_h2d_0.4.json',
            'printer_templates/bambu_p2s_0.4.json', 'printer_templates/voron2.4_300_0.4.json',
        },
        'templates': {'index.html'},
        'static': {
            'app.css', 'app.js', 'explode.js', 'i18n.js', 'local-preview-worker.js', 'local-preview.js',
            'preview-lighting.js', 'preview-palette.js', 'site.css',
            'skin-preview-template.js', 'theme.js', 'vendor/three.min.js', 'viewer.js',
        },
    }
    for directory, filenames in expected.items():
        base = ROOT / directory
        actual = {
            p.relative_to(base).as_posix() for p in base.rglob('*')
            if p.is_file() and '__pycache__' not in p.relative_to(base).parts
        }
        assert actual == filenames

def test_missing_cad_returns_actionable_error_and_releases_lock(client, monkeypatch):
    def unavailable(*args):
        raise ModuleNotFoundError('cadquery')
    monkeypatch.setattr(body, 'generate', unavailable)
    response = client.post('/api/generate', data=form())
    assert response.status_code == 503 and 'requirements.txt' in response.json['error']
    assert not web._generation_lock.locked()

@pytest.mark.cad
@pytest.mark.parametrize('model', ['steve','alex'])
def test_native_step_to_real_print_project(tmp_path, model):
    pytest.importorskip('cadquery')
    path = tmp_path/'skin.png'; path.write_bytes(skin_bytes())
    mesh = body.generate(path, model, 2.5, 8)
    preview = body.preview(mesh)
    assert preview['triangles'] > 10000
    assert len({r['file'] for r in preview['parts']}) == 51
    assert len({r['file'] for r in preview['parts'] if r['part'] == 'head'}) > 1
    assert {s['source_file'].split('/')[0] for s in mesh['solids']} == {'head','body','left_arm','right_arm','left_leg','right_leg'}
    target = tmp_path/'body.3mf'; body.export(mesh,target,'bambu_A1_0.4')
    with zipfile.ZipFile(target) as archive:
        config = archive.read('Metadata/model_settings.config').decode()
        assert 'chest_mutile_color_for_print.stp' in config and 'joint_rods/' in config
        assert len([n for n in archive.namelist() if n.startswith('3D/Objects/')]) > 20


def test_preview_preserves_source_parts_and_scaled_entity_centers():
    solids = []
    for source, origin in [('head/shell.stp', (0, 0, 0)),
                           ('head/shell.stp', (0, 0, 2)),
                           ('head/frame.stp', (6, 0, 0))]:
        x, y, z = origin
        solids.append({'positions': [x, y, z, x+3, y, z, x, y+3, z],
                       'position_scale': 2, 'tri_extruders': [1], 'source_file': source})
    mesh = {'solids': solids, 'palette': [[255, 255, 255]]}
    before = json.dumps(mesh)
    result = body.preview(mesh)
    assert [r['file'] for r in result['parts']] == ['head/shell.stp', 'head/shell.stp', 'head/frame.stp']
    assert [r['part'] for r in result['parts']] == ['head'] * 3
    assert [(r['start'], r['count']) for r in result['parts']] == [(0, 3), (3, 3), (6, 3)]
    assert [r['center'] for r in result['parts']] == [[2, 2, 0], [2, 2, 4], [14, 2, 0]]
    assert json.dumps(mesh) == before
