"""Shared RGB to Lab conversion for the ordinary-body palette."""
import numpy as np

def _srgb_to_linear(c):
    """sRGB (0..1) -> linear reflectance (0..1)."""
    c = np.clip(np.asarray(c, dtype=float), 0.0, 1.0)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

def _rgb_to_lab(rgb_array):
    """Convert RGB (0-255) to CIE Lab color space for perceptual quantization."""
    # Normalize to 0-1, then sRGB -> linear
    rgb = _srgb_to_linear(rgb_array.astype(np.float64) / 255.0)

    # Linear RGB to XYZ (D65)
    mat = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ])
    xyz = rgb @ mat.T

    # XYZ to Lab
    ref = np.array([0.95047, 1.0, 1.08883])
    xyz = xyz / ref

    mask = xyz > 0.008856
    xyz[mask] = xyz[mask] ** (1.0 / 3.0)
    xyz[~mask] = 7.787 * xyz[~mask] + 16.0 / 116.0

    L = 116.0 * xyz[:, 1] - 16.0
    a = 500.0 * (xyz[:, 0] - xyz[:, 1])
    b = 200.0 * (xyz[:, 1] - xyz[:, 2])

    return np.stack([L, a, b], axis=1)
