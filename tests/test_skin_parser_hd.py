"""HD sampling keeps source subpixels without changing canonical callers."""

import numpy as np
import pytest
from PIL import Image

from voxfigure.skin_parser import SkinParser, detect_model_type


def save_skin(tmp_path, pixels):
    path = tmp_path / 'skin.png'
    Image.fromarray(pixels, 'RGBA').save(path)
    return path


def coordinate_skin(size=128):
    y, x = np.indices((size, size))
    return np.stack((x, y, (x + y) % 256, np.full_like(x, 255)), axis=-1).astype(np.uint8)


def test_four_hd_subpixels_remain_independent(tmp_path):
    pixels = np.zeros((128, 128, 4), dtype=np.uint8)
    colors = [[255, 0, 0, 255], [0, 255, 0, 255],
              [0, 0, 255, 255], [255, 255, 0, 0]]
    pixels[16:18, 16:18] = np.array(colors).reshape(2, 2, 4)
    skin = SkinParser(save_skin(tmp_path, pixels))
    assert skin.texture_scale == 2 and skin.pixels.shape == (128, 128, 4)
    actual = [skin.get_face_color('head', 'inner', 'front', 15, y, 15-z,
                                 (16, 16, 16), texture_scale=2)
              for z in range(2) for y in range(2)]
    assert actual == [tuple(c) for c in colors]
    # Existing canonical callers still receive one representative sample.
    assert skin.get_face_color('head', 'inner', 'front', 7, 0, 7, (8, 8, 8)) == tuple(colors[3])


@pytest.mark.parametrize('face,xy', [
    ('front', (89, 41)), ('back', (106, 41)),
    ('right', (87, 41)), ('left', (94, 41)),
    ('top', (89, 39)), ('bottom', (98, 39)),
])
def test_hd_alex_arm_six_faces_match_scalar_and_batch(tmp_path, face, xy):
    skin = SkinParser(save_skin(tmp_path, coordinate_skin()), 'alex')
    expected = (*xy, sum(xy), 255)
    assert skin.get_face_color('right_arm', 'inner', face, 7, 1, 22,
                               (8, 6, 24), texture_scale=2) == expected
    actual = skin.get_face_colors_batch('right_arm', 'inner', face,
                                        np.array([7]), np.array([1]), np.array([22]),
                                        (8, 6, 24), texture_scale=2)
    np.testing.assert_array_equal(actual, [expected])


@pytest.mark.parametrize('size', [64, 128])
def test_model_detection_checks_all_subpixels_in_exclusive_column(tmp_path, size):
    pixels = np.zeros((size, size, 4), dtype=np.uint8)
    path = save_skin(tmp_path, pixels)
    assert detect_model_type(path) == 'alex'
    scale = size // 64
    pixels[32*scale-1, 55*scale-1, 3] = 255
    assert detect_model_type(save_skin(tmp_path, pixels)) == 'steve'


def test_64_uv_and_legacy_outer_semantics_unchanged(tmp_path):
    skin = SkinParser(save_skin(tmp_path, coordinate_skin(64)))
    assert skin.texture_scale == 1
    assert skin.get_face_color('head', 'inner', 'front', 7, 0, 7, (8, 8, 8)) == (8, 8, 16, 255)
    legacy = SkinParser(save_skin(tmp_path, coordinate_skin(64)[:32]))
    assert legacy.is_legacy
    assert legacy.get_face_color('body', 'outer', 'front', 3, 0, 11, (4, 8, 12)) == (0, 0, 0, 0)


def test_128_legacy_has_native_head_overlay_but_no_body_overlay(tmp_path):
    skin = SkinParser(save_skin(tmp_path, coordinate_skin()[:64]))
    assert skin.texture_scale == 2 and skin.is_legacy
    assert skin.get_face_color('head', 'outer', 'front', 15, 0, 15,
                               (16, 16, 16), texture_scale=2) == (80, 16, 96, 255)
    assert skin.get_face_color('body', 'outer', 'front', 7, 0, 23,
                               (8, 16, 24), texture_scale=2) == (0, 0, 0, 0)


@pytest.mark.parametrize('size', [64, 128])
@pytest.mark.parametrize('part', ['arm', 'leg'])
@pytest.mark.parametrize('face,source_face', [('front', 'front'), ('back', 'back'),
                                             ('left', 'right'), ('right', 'left'),
                                             ('top', 'top'), ('bottom', 'bottom')])
def test_legacy_left_limbs_mirror_right_uv_in_scalar_and_batch(tmp_path, size, part, face, source_face):
    scale = size // 64
    skin = SkinParser(save_skin(tmp_path, coordinate_skin(size)[:size//2]))
    dims = (4*scale, 4*scale, 12*scale)
    ix, iy, iz = dims[0]-1, 1, dims[2]-2
    expected = skin.get_face_color('right_'+part, 'inner', source_face,
                                   ix, dims[1]-1-iy, iz, dims, texture_scale=scale)
    assert expected[3] == 255
    assert skin.get_face_color('left_'+part, 'inner', face, ix, iy, iz,
                               dims, texture_scale=scale) == expected
    actual = skin.get_face_colors_batch('left_'+part, 'inner', face,
                                        np.array([ix]), np.array([iy]), np.array([iz]),
                                        dims, texture_scale=scale)
    np.testing.assert_array_equal(actual, [expected])
