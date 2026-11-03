import json
from pathlib import Path
import shutil
import subprocess
import numpy as np
import pytest
from voxfigure.detail_palette import quantize_rgb
from voxfigure.step_colorizer import quantize_color_indices

NEUTRAL_ACCENTS = [[78,69,67],[255,255,255],[189,189,189],[199,199,199],
 [229,216,213],[234,234,234],[175,175,175],[255,251,250],[165,165,165],
 [127,126,126],[224,224,224],[181,181,181],[176,176,176],[108,98,96],
 [255,207,207],[158,158,158],[178,178,178],[237,237,237],[230,199,155],
 [82,70,67],[93,82,80]]


def test_five_colors_preserve_small_accents_and_light_dark_contrast():
    source=np.array(NEUTRAL_ACCENTS)
    # Only two gold and four pink samples amid many surface/triangle samples.
    colors=np.concatenate([np.repeat(source[:10],100,axis=0),source[10:],
                           [[230,199,155]],[[255,207,207]]*3])
    palette,labels=quantize_rgb(colors,5)
    assert len(palette)==5
    for detail in ([78,69,67],[255,255,255],[230,199,155],[255,207,207]):
        assert detail in palette
        assert np.all(np.asarray(palette)[labels[np.all(colors==detail,axis=1)]]==detail)
    assert all(c in NEUTRAL_ACCENTS for c in palette)
    # Keep the dark belt/neck distinguishable from adjacent jacket gray.
    for color,expected in [([127,126,126],[78,69,67]),([189,189,189],[175,175,175]),
                           ([229,216,213],[255,255,255])]:
        assert np.all(np.asarray(palette)[labels[np.all(colors==color,axis=1)]]==expected)


def test_palette_is_order_and_tessellation_independent_and_idempotent():
    colors=np.array(NEUTRAL_ACCENTS)
    p,idx=quantize_rgb(colors,5)
    repeated=np.repeat(colors,np.arange(1,len(colors)+1),axis=0)[::-1]
    assert quantize_rgb(repeated,5)[0]==p
    assert quantize_rgb(colors[::-1],5)[1].tolist()==idx[::-1].tolist()
    mapped=np.asarray(p)[idx]
    again,labels=quantize_rgb(mapped,5)
    assert np.array_equal(np.asarray(again)[labels],mapped)
    # Float32 input must not truncate source channels one level darker.
    floats=(colors/255).astype(np.float32)
    assert quantize_color_indices(floats.ravel(),5)[0]==p
    assert quantize_color_indices(floats.ravel(),32)[0]==sorted(NEUTRAL_ACCENTS)




@pytest.mark.parametrize('k',[1,2,3,5,8,32,256,512])
def test_budget_exact_colors_and_edge_cases(k):
    colors=np.array(NEUTRAL_ACCENTS)
    palette,labels=quantize_rgb(colors,k)
    assert len(palette)<=k and labels.max()<len(palette)
    if k>=len(colors):assert np.array_equal(np.asarray(palette)[labels],colors)
    assert quantize_rgb([],k)[0]==[]
    assert quantize_rgb([[17,29,41]]*20,k)[0]==[[17,29,41]]


