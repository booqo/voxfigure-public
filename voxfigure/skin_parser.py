"""Parse Minecraft skin PNG and provide UV-mapped color lookups."""

import numpy as np
from PIL import Image


# UV mapping tables: (start_x, start_y, width, height)
# Format: UV_MAP[layer][part][face] = (sx, sy, w, h)
# For Alex, only arms differ - handled via ALEX_ARM_UV

UV_MAP = {
    "inner": {
        "head": {
            "top":    (8, 0, 8, 8),
            "bottom": (16, 0, 8, 8),
            "right":  (0, 8, 8, 8),
            "front":  (8, 8, 8, 8),
            "left":   (16, 8, 8, 8),
            "back":   (24, 8, 8, 8),
        },
        "body": {
            "top":    (20, 16, 8, 4),
            "bottom": (28, 16, 8, 4),
            "right":  (16, 20, 4, 12),
            "front":  (20, 20, 8, 12),
            "left":   (28, 20, 4, 12),
            "back":   (32, 20, 8, 12),
        },
        "right_arm": {
            "top":    (44, 16, 4, 4),
            "bottom": (48, 16, 4, 4),
            "right":  (40, 20, 4, 12),
            "front":  (44, 20, 4, 12),
            "left":   (48, 20, 4, 12),
            "back":   (52, 20, 4, 12),
        },
        "left_arm": {
            "top":    (36, 48, 4, 4),
            "bottom": (40, 48, 4, 4),
            "right":  (32, 52, 4, 12),
            "front":  (36, 52, 4, 12),
            "left":   (40, 52, 4, 12),
            "back":   (44, 52, 4, 12),
        },
        "right_leg": {
            "top":    (4, 16, 4, 4),
            "bottom": (8, 16, 4, 4),
            "right":  (0, 20, 4, 12),
            "front":  (4, 20, 4, 12),
            "left":   (8, 20, 4, 12),
            "back":   (12, 20, 4, 12),
        },
        "left_leg": {
            "top":    (20, 48, 4, 4),
            "bottom": (24, 48, 4, 4),
            "right":  (16, 52, 4, 12),
            "front":  (20, 52, 4, 12),
            "left":   (24, 52, 4, 12),
            "back":   (28, 52, 4, 12),
        },
    },
    "outer": {
        "head": {
            "top":    (40, 0, 8, 8),
            "bottom": (48, 0, 8, 8),
            "right":  (32, 8, 8, 8),
            "front":  (40, 8, 8, 8),
            "left":   (48, 8, 8, 8),
            "back":   (56, 8, 8, 8),
        },
        "body": {
            "top":    (20, 32, 8, 4),
            "bottom": (28, 32, 8, 4),
            "right":  (16, 36, 4, 12),
            "front":  (20, 36, 8, 12),
            "left":   (28, 36, 4, 12),
            "back":   (32, 36, 8, 12),
        },
        "right_arm": {
            "top":    (44, 32, 4, 4),
            "bottom": (48, 32, 4, 4),
            "right":  (40, 36, 4, 12),
            "front":  (44, 36, 4, 12),
            "left":   (48, 36, 4, 12),
            "back":   (52, 36, 4, 12),
        },
        "left_arm": {
            "top":    (52, 48, 4, 4),
            "bottom": (56, 48, 4, 4),
            "right":  (48, 52, 4, 12),
            "front":  (52, 52, 4, 12),
            "left":   (56, 52, 4, 12),
            "back":   (60, 52, 4, 12),
        },
        "right_leg": {
            "top":    (4, 32, 4, 4),
            "bottom": (8, 32, 4, 4),
            "right":  (0, 36, 4, 12),
            "front":  (4, 36, 4, 12),
            "left":   (8, 36, 4, 12),
            "back":   (12, 36, 4, 12),
        },
        "left_leg": {
            "top":    (4, 48, 4, 4),
            "bottom": (8, 48, 4, 4),
            "right":  (0, 52, 4, 12),
            "front":  (4, 52, 4, 12),
            "left":   (8, 52, 4, 12),
            "back":   (12, 52, 4, 12),
        },
    },
}

# Alex arm UV overrides (only arms differ, width=3 instead of 4)
ALEX_ARM_UV = {
    "inner": {
        "right_arm": {
            "top":    (44, 16, 3, 4),
            "bottom": (47, 16, 3, 4),
            "right":  (40, 20, 4, 12),
            "front":  (44, 20, 3, 12),
            "left":   (47, 20, 4, 12),
            "back":   (51, 20, 3, 12),
        },
        "left_arm": {
            "top":    (36, 48, 3, 4),
            "bottom": (39, 48, 3, 4),
            "right":  (32, 52, 4, 12),
            "front":  (36, 52, 3, 12),
            "left":   (39, 52, 4, 12),
            "back":   (43, 52, 3, 12),
        },
    },
    "outer": {
        "right_arm": {
            "top":    (44, 32, 3, 4),
            "bottom": (47, 32, 3, 4),
            "right":  (40, 36, 4, 12),
            "front":  (44, 36, 3, 12),
            "left":   (47, 36, 4, 12),
            "back":   (51, 36, 3, 12),
        },
        "left_arm": {
            "top":    (52, 48, 3, 4),
            "bottom": (55, 48, 3, 4),
            "right":  (48, 52, 4, 12),
            "front":  (52, 52, 3, 12),
            "left":   (55, 52, 4, 12),
            "back":   (59, 52, 3, 12),
        },
    },
}

FACES = ["front", "back", "right", "left", "top", "bottom"]

# Arm textures are split at the elbow for articulated segments. Each segment keeps
# its own half of the arm texture, so the texel density is unchanged and the
# shoulder cap / hand cap stay exactly where they were. Fractions are measured
# from the shoulder (skin v grows toward the hand).
_ARM_SEGMENTS = {
    "right_arm": ("right_arm", 0.0, 0.5),
    "right_forearm": ("right_arm", 0.5, 1.0),
    "left_arm": ("left_arm", 0.0, 0.5),
    "left_forearm": ("left_arm", 0.5, 1.0),
}


def part_uv(part, model_type, layer):
    """Face UV rects for one body part, slicing the arm segments at the elbow.

    Only the side faces are cut vertically; the exposed shoulder/hand caps keep
    their originals and the internal cut faces reuse a cap (they end up inside
    the fused solid and are never sampled for a visible surface).
    """
    source, low, high = _ARM_SEGMENTS.get(part, (part, 0.0, 1.0))
    table = ALEX_ARM_UV if model_type == "alex" else UV_MAP
    rects = table.get(layer, {}).get(source)
    if rects is None or (low == 0.0 and high == 1.0):
        return UV_MAP[layer][source]
    upper = low == 0.0
    sliced = {}
    for face, (sx, sy, width, height) in rects.items():
        if face in ("top", "bottom"):
            continue
        offset = int(round(height * low))
        sliced[face] = (sx, sy + offset, width,
                        int(round(height * (high - low))))
    sliced["top"] = rects["top"] if upper else rects["bottom"]
    sliced["bottom"] = rects["bottom"] if not upper else rects["top"]
    return sliced


# Voxel (ix, iy, iz) → UV-region offset for each face. Maps grid index into
# the local (du, dv) within a face's UV patch. Add to (sx, sy) for the final
# pixel. Shared between SkinParser and ArmorTexture so the math stays in one
# place — a past divergence here would silently swap eye/back textures.
_FACE_PIXEL_OFFSET = {
    "front":  lambda ix, iy, iz, dx, wy, hz: (iy,           hz - 1 - iz),
    "back":   lambda ix, iy, iz, dx, wy, hz: (wy - 1 - iy,  hz - 1 - iz),
    "right":  lambda ix, iy, iz, dx, wy, hz: (ix,           hz - 1 - iz),
    "left":   lambda ix, iy, iz, dx, wy, hz: (dx - 1 - ix,  hz - 1 - iz),
    "top":    lambda ix, iy, iz, dx, wy, hz: (iy,           ix),
    "bottom": lambda ix, iy, iz, dx, wy, hz: (wy - 1 - iy,  ix),
}


def face_uv_to_pixel(face, ix, iy, iz, part_dims, face_uv):
    """Map voxel grid index → texture pixel for one face. Returns (px, py) or
    None if face is unknown. `face_uv` is (sx, sy, w, h); only sx/sy used."""
    fn = _FACE_PIXEL_OFFSET.get(face)
    if fn is None:
        return None
    du, dv = fn(ix, iy, iz, *part_dims)
    return face_uv[0] + du, face_uv[1] + dv


def detect_model_type(png_path: str) -> str:
    """Auto-detect Steve vs Alex from skin PNG.

    Steve has 4px wide arms, Alex has 3px. The key difference in UV layout:
    - Steve right arm back face: (52,20) width 4 → cols 52-55
    - Alex right arm back face: (51,20) width 3 → cols 51-53
    Column 54, rows 20-31 has opaque pixels in Steve, transparent in Alex.
    """
    img = Image.open(png_path).convert("RGBA")
    pixels = np.array(img)
    scale = img.width // 64 if img.width >= 64 and img.width % 64 == 0 else 1
    if img.height == img.width and img.width >= 64:
        # Inspect every subpixel of the Steve-only column in an HD atlas.
        arm_col = pixels[20 * scale:32 * scale, 54 * scale:55 * scale, 3]
        if np.any(arm_col > 0):
            return "steve"
    return "alex"


class SkinParser:
    def __init__(self, png_path: str, model_type: str = "steve"):
        img = Image.open(png_path).convert("RGBA")
        self.width, self.height = img.size
        self.pixels = np.array(img)  # shape: (H, W, 4)
        self.model_type = model_type
        self.texture_scale = (self.width // 64
                              if self.width >= 64 and self.width % 64 == 0
                              and self.height in (self.width, self.width // 2)
                              else 1)
        self.is_legacy = (self.height == 32 * self.texture_scale)

        # Build effective UV map
        self.uv = {}
        for layer in ["inner", "outer"]:
            self.uv[layer] = {}
            for part in UV_MAP[layer]:
                if model_type == "alex" and "arm" in part and layer in ALEX_ARM_UV and part in ALEX_ARM_UV[layer]:
                    self.uv[layer][part] = ALEX_ARM_UV[layer][part]
                else:
                    self.uv[layer][part] = UV_MAP[layer][part]

    def get_pixel(self, px: int, py: int) -> tuple:
        """Get RGBA pixel at (px, py). Returns (0,0,0,0) if out of bounds."""
        if 0 <= px < self.width and 0 <= py < self.height:
            return tuple(self.pixels[py, px])
        return (0, 0, 0, 0)

    def get_face_color(self, part: str, layer: str, face: str,
                       ix: int, iy: int, iz: int,
                       part_dims: tuple, texture_scale: int = 1) -> tuple:
        """
        Get the RGBA color for a specific face of a voxel.

        Args:
            part: body part name
            layer: "inner" or "outer"
            face: face name (front/back/right/left/top/bottom)
            ix, iy, iz: grid indices within the part (0-based)
            part_dims: (depth_x, width_y, height_z) of the part
            texture_scale: resolution of the supplied indices/dimensions. Use
                self.texture_scale with an HD grid to keep every source pixel;
                the default samples a canonical grid for existing callers.
        """
        if self.is_legacy and layer == "outer" and part != "head":
            # Legacy skins only have head outer layer
            return (0, 0, 0, 0)

        if self.is_legacy and part.startswith("left_"):
            part = part.replace("left_", "right_", 1)
            iy = part_dims[1] - 1 - iy
            face = {"left": "right", "right": "left"}.get(face, face)

        if layer not in self.uv or part not in self.uv[layer]:
            return (0, 0, 0, 0)

        face_uv = self.uv[layer][part].get(face)
        if face_uv is None:
            return (0, 0, 0, 0)
        pix = face_uv_to_pixel(face, ix, iy, iz, part_dims, face_uv)
        if pix is None:
            return (0, 0, 0, 0)
        px, py = self._source_pixel(*pix, face_uv, texture_scale)
        return self.get_pixel(int(px), int(py))

    def _source_pixel(self, px, py, face_uv, texture_scale):
        """Map a sampling grid into the unchanged source image, scalar or batch."""
        if texture_scale not in (1, self.texture_scale):
            raise ValueError("Skin sampling scale does not match its texture")
        if texture_scale == self.texture_scale:
            return (px + face_uv[0] * (self.texture_scale - 1),
                    py + face_uv[1] * (self.texture_scale - 1))
        step = self.texture_scale / texture_scale
        # A canonical-grid caller uses the centre of each HD pixel block,
        # matching nearest-neighbour canvas downsampling. Native HD callers
        # use step=1, so adjacent subpixels remain independent.
        return (face_uv[0] * self.texture_scale
                + np.floor((px - face_uv[0] + 0.5) * step).astype(np.int64),
                face_uv[1] * self.texture_scale
                + np.floor((py - face_uv[1] + 0.5) * step).astype(np.int64))

    def get_face_colors_batch(self, part: str, layer: str, face: str,
                              ix, iy, iz, part_dims: tuple, texture_scale: int = 1):
        """Vectorized get_face_color: ix/iy/iz are equal-length integer arrays.

        Returns an (n, 4) uint8 RGBA array; rows fall back to (0,0,0,0) exactly
        like the scalar path (legacy outer layer, unknown part/face,
        out-of-bounds pixel)."""
        out = np.zeros((len(ix), 4), dtype=np.uint8)
        if self.is_legacy and layer == "outer" and part != "head":
            return out
        if self.is_legacy and part.startswith("left_"):
            part = part.replace("left_", "right_", 1)
            iy = part_dims[1] - 1 - iy
            face = {"left": "right", "right": "left"}.get(face, face)
        face_uv = self.uv.get(layer, {}).get(part, {}).get(face)
        fn = _FACE_PIXEL_OFFSET.get(face)
        if face_uv is None or fn is None:
            return out
        du, dv = fn(ix, iy, iz, *part_dims)   # the offset lambdas are pure arithmetic
        px, py = self._source_pixel(face_uv[0] + du, face_uv[1] + dv,
                                    face_uv, texture_scale)
        ok = (px >= 0) & (px < self.width) & (py >= 0) & (py < self.height)
        if ok.any():
            out[ok] = self.pixels[py[ok], px[ok]]
        return out

    def get_all_face_colors(self, part: str, layer: str,
                            ix: int, iy: int, iz: int,
                            part_dims: tuple, texture_scale: int = 1) -> dict:
        """Get colors for all 6 faces of a voxel."""
        return {
            face: self.get_face_color(part, layer, face, ix, iy, iz, part_dims,
                                      texture_scale=texture_scale)
            for face in FACES
        }
