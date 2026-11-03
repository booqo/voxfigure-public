"""Deterministic source-color palettes for small-budget pixel-art printing.

Distinct colors have equal influence: triangle density/duplicate samples must
not drown small eyes or accents. Preserve luminance endpoints for high-contrast
art, seed uncovered colors, refine to source-color medoids, then select the
candidate balancing mean error with worst-color error. No dithering or invented
blended filament colors. Numerically paired with static/preview-palette.js.
"""
import numpy as np

REVISION = 1


def perceptual_points(rgb):
    from .color_quantizer import _rgb_to_lab
    # Slightly favor hue/chroma over shading. Fixed precision makes JS/Python
    # decisions independent of libm's final floating-point bits.
    return np.floor(_rgb_to_lab(np.asarray(rgb, dtype=float))*[.8,1.15,1.15]*1000+.5)/1000


def _distance(points, center):
    return ((points-center)**2).sum(axis=-1)


def _assign(points, centers, preserve_tones=False):
    labels=np.zeros(len(points),dtype=np.intp)
    best=np.full(len(points),np.inf)
    for j,center in enumerate(centers):
        d=_distance(points,center)
        if preserve_tones:
            # Erasing a dark line into its lighter surround is more damaging
            # to small pixel-art details than approximating it a little darker.
            d += np.where(points[:,0]<48, np.maximum(center[0]-points[:,0],0)**2, 0)
        update=d<best-1e-9
        best[update]=d[update];labels[update]=j
    return labels,best


def _fit(points, k):
    dark=int(points[:,0].argmin());light=int(points[:,0].argmax())
    anchors=[dark,light] if k>=3 and points[light,0]-points[dark,0]>=32 else []
    seeds=list(dict.fromkeys([dark,light,int(_distance(points,points.mean(axis=0)).argmin())]))
    best_ids=None;best_score=float('inf')
    for seed in seeds:
        ids=list(dict.fromkeys(anchors+[seed]))[:k]
        _,dist=_assign(points,points[ids])
        while len(ids)<k:
            remaining=dist.copy();remaining[ids]=-1
            ids.append(int(remaining.argmax()))
            dist=np.minimum(dist,_distance(points,points[ids[-1]]))
        for _ in range(8):
            labels,_=_assign(points,points[ids]);updated=ids.copy()
            for j,old in enumerate(ids):
                if old in anchors:continue
                members=np.flatnonzero(labels==j)
                if not len(members):continue
                cluster=points[members]
                candidate=int(members[_distance(cluster,cluster.mean(axis=0)).argmin()])
                if _distance(cluster,points[candidate]).mean()<_distance(cluster,points[old]).mean()-1e-9:
                    updated[j]=candidate
            if updated==ids:break
            ids=updated
        _,dist=_assign(points,points[ids])
        score=float(dist.mean()+.25*dist.max())
        if score<best_score-1e-9:best_ids=ids;best_score=score
    return sorted(set(best_ids))


def quantize_rgb(rgb, max_colors=8):
    """0..255 RGB samples -> exact source palette, compact per-sample indices."""
    if isinstance(max_colors,bool) or int(max_colors)!=max_colors or not 1<=max_colors<=512:
        raise ValueError('Color count must be between 1 and 512')
    arr=np.asarray(rgb,dtype=float).reshape(-1,3)
    if not np.isfinite(arr).all():raise ValueError('Non-finite colors')
    arr=np.floor(np.clip(arr,0,255)+.5).astype(np.int64)
    codes,inverse=np.unique((arr[:,0]<<16)|(arr[:,1]<<8)|arr[:,2],return_inverse=True)
    unique=np.stack([(codes>>16)&255,(codes>>8)&255,codes&255],axis=1)
    if len(unique)<=max_colors:return unique.tolist(),inverse
    points=perceptual_points(unique)
    ids=_fit(points,int(max_colors))
    labels,_=_assign(points,points[ids],preserve_tones=True)
    return unique[ids].tolist(),labels[inverse]
