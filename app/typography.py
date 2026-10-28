"""Bundled OFL fonts: measured glyphs and portable outlines for album exports."""
from functools import lru_cache
from html import escape
from pathlib import Path

FONTS = {'classic':'CrimsonText-Regular.ttf', 'italic':'CrimsonText-Italic.ttf',
         'script':'MarckScript-Regular.ttf'}


@lru_cache(maxsize=3)
def font(key):
    from fontTools.ttLib import TTFont
    return TTFont(Path(__file__).parent/'fonts'/FONTS[key])


def width(text, size, key='ui'):
    if key == 'ui':
        # Conservative sans-serif advances; unlike the former full-width estimate,
        # narrow letters and spaces do not reserve large empty boxes.
        return sum(.32 if c in ' ilI.,\'’' else 1.12 if c in 'WMwm' or ord(c)>0x2ff
                   else .9 if c.isupper() else .72 for c in text)*size
    f=font(key); cmap=f.getBestCmap(); metrics=f['hmtx'].metrics
    return sum(metrics[cmap.get(ord(c),'.notdef')][0] for c in text)*size/f['head'].unitsPerEm


@lru_cache(maxsize=1024)
def glyph_path(key, name):
    from fontTools.pens.svgPathPen import SVGPathPen
    glyphs=font(key).getGlyphSet(); pen=SVGPathPen(glyphs); glyphs[name].draw(pen)
    return pen.getCommands()


@lru_cache(maxsize=1024)
def vertical_metrics(text, key='ui'):
    if key=='ui':return .85,.25
    from fontTools.pens.boundsPen import BoundsPen
    f=font(key); glyphs=f.getGlyphSet(); cmap=f.getBestCmap(); bottom=top=0
    for c in text:
        pen=BoundsPen(glyphs); glyphs[cmap.get(ord(c),'.notdef')].draw(pen)
        if pen.bounds:
            bottom=min(bottom,pen.bounds[1]);top=max(top,pen.bounds[3])
    upem=f['head'].unitsPerEm
    return top/upem,-bottom/upem


def outlined(text, x, y, size, key, color='#302d28'):
    """Paths avoid browser/fontconfig substitutions; the title retains full text."""
    from fontTools.pens.svgPathPen import SVGPathPen
    f=font(key); glyphs=f.getGlyphSet(); cmap=f.getBestCmap()
    scale=size/f['head'].unitsPerEm; cursor=0; out=[]
    for c in text:
        name=cmap.get(ord(c),'.notdef'); d=glyph_path(key,name)
        if d:out.append(f'<path d="{d}" transform="translate({cursor} 0)"/>')
        cursor+=f['hmtx'].metrics[name][0]
    return (f'<g role="img" aria-label="{escape(text,quote=True)}" fill="{color}" '
            f'transform="translate({x} {y}) scale({scale} {-scale})">'
            f'<title>{escape(text)}</title>'+''.join(out)+'</g>')
