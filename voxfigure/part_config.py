"""Part geometry configuration for STEP processing.

Each body part has: grid dimensions, center offset, outer expansion ratio.
All values in pixels (multiply by pixel_size for mm).
"""

BASE_PIXEL_SIZE = 2.5  # inner_box_override values are designed for this pixel size

PART_DEFS = {
    "head": {
        "grid": (8, 8, 8),
        "center": (0, 0, 4),
        "outer_expand": 0.5,
    },
    "body": {
        "grid": (4, 8, 12),
        "center": (0, 0, -6),
        "outer_expand": 0.25,
        "inner_box_override": ([-16/3, -10, -30.1666667], [16/3, 10, 0]),
    },
    "right_arm": {
        "grid_steve": (4, 4, 12),
        "grid_alex": (4, 3, 12),
        "center": (0, -6, -6),         # Steve: 4px wide, centred at y=-6 → y∈[-8,-4]px
        "center_alex": (0, -5.5, -6),  # Alex: 3px wide, shares the y=-4px body edge → y∈[-7,-4]px
        "outer_expand": 0.25,
        "inner_box_override_steve": ([-5, -20, -30.2], [5, -10, 0]),
        "inner_box_override_alex": ([-5, -17.5, -30.2], [5, -10, 0]),
    },
    "left_arm": {
        "grid_steve": (4, 4, 12),
        "grid_alex": (4, 3, 12),
        "center": (0, 6, -6),
        "center_alex": (0, 5.5, -6),   # Alex: 3px wide, shares the y=+4px body edge → y∈[+4,+7]px
        "outer_expand": 0.25,
        "inner_box_override_steve": ([-5, 10, -30.2], [5, 20, 0]),
        "inner_box_override_alex": ([-5, 10, -30.2], [5, 17.5, 0]),
    },
    "right_leg": {
        "grid": (4, 4, 12),
        "center": (0, -2, -18),
        "outer_expand": 0.25,
        "inner_box_override": ([-5, -10, -60.0666666], [5, 0, -30]),
    },
    "left_leg": {
        "grid": (4, 4, 12),
        "center": (0, 2, -18),
        "outer_expand": 0.25,
        "inner_box_override": ([-5, 0, -60.0666666], [5, 10, -30]),
    },
}


def _model_def(pdef, base, model_type):
    """pdef['{base}_{model_type}'] if present, else pdef['{base}'], else None.
    Lets a part override grid/center/inner_box per model (e.g. Alex's 3px arms)."""
    return pdef.get(f"{base}_{model_type}", pdef.get(base))


def standing_height_pixels(model_type="alex"):
    """Standing figure envelope including the complete skin overlay.

    Use the skin grid, not classification-box fitting tolerances. This matches
    the authored full STEP envelope (Z=-60.625..21.25 at 2.5mm/px). Alpha
    trimming can reduce the printed height; armor/accessories are excluded.
    """
    bounds = []
    for pdef in PART_DEFS.values():
        center_z = _model_def(pdef, "center", model_type)[2]
        half_height = _model_def(pdef, "grid", model_type)[2] / 2 + pdef["outer_expand"]
        bounds.append((center_z - half_height, center_z + half_height))
    return max(hi for _, hi in bounds) - min(lo for lo, _ in bounds)


def make_grid(grid_dims, center_mm, voxel_sizes):
    """Per-axis world-space voxel-center coords for one layer.

    Returns 3 lists; list[ax][i] = center of voxel i along axis ax. Shared by
    voxel_model.generate_voxels and step_colorizer.color_solids so the quick
    preview and the Generate-3D STEP model build identical grids.
    """
    grids = []
    for ax in range(3):
        n = grid_dims[ax]
        half = n * voxel_sizes[ax] / 2.0
        grids.append([center_mm[ax] - half + (i + 0.5) * voxel_sizes[ax] for i in range(n)])
    return grids


def get_part_config(part: str, model_type: str = "steve", pixel_size: float = 2.5) -> dict:
    """Get resolved part configuration with mm values.

    Returns dict:
        grid: (gx, gy, gz)
        center_mm: (cx, cy, cz) in mm
        part_dims: (gx, gy, gz) for skin UV lookup
        inner_box_min/max: [x,y,z] in mm
        outer_voxel_sizes: (ox, oy, oz) in mm
        outer_box_min/max: [x,y,z] in mm
        pixel_size: float
    """
    pdef = PART_DEFS[part]

    grid = _model_def(pdef, "grid", model_type)
    gx, gy, gz = grid

    # UV-grid center: model-specific where given. Alex's 3px arm sits differently
    # than Steve's 4px arm, so it needs its own center for the UV grid to line up
    # with the geometry — otherwise hand/arm triangles snap to the wrong texture column.
    cx, cy, cz = _model_def(pdef, "center", model_type)
    center_mm = (cx * pixel_size, cy * pixel_size, cz * pixel_size)

    # Classification box: explicit override if the part has one, else the grid extent.
    box = _model_def(pdef, "inner_box_override", model_type)
    if box:
        scale = pixel_size / BASE_PIXEL_SIZE
        inner_box_min = [v * scale for v in box[0]]
        inner_box_max = [v * scale for v in box[1]]
    else:
        inner_half = [gx * pixel_size / 2, gy * pixel_size / 2, gz * pixel_size / 2]
        inner_box_min = [center_mm[i] - inner_half[i] for i in range(3)]
        inner_box_max = [center_mm[i] + inner_half[i] for i in range(3)]

    # Outer: expand classification box by outer_expand pixels per side
    expand = pdef["outer_expand"]
    expand_mm = expand * pixel_size
    outer_box_min = [inner_box_min[i] - expand_mm for i in range(3)]
    outer_box_max = [inner_box_max[i] + expand_mm for i in range(3)]

    return {
        "grid": grid,
        "part_dims": grid,
        "outer_expand": expand,
        "center_mm": center_mm,
        "pixel_size": pixel_size,
        "inner_box_min": inner_box_min,
        "inner_box_max": inner_box_max,
        "outer_box_min": outer_box_min,
        "outer_box_max": outer_box_max,
    }
