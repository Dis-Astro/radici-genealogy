"""Shared canvas and print geometry. Coordinates are CSS pixels (96 dpi)."""
import math
from html import escape
from .typography import width as text_width, outlined, vertical_metrics

W, H, GAP = 224, 96, 32


def finite(value, lo, hi):
    n = float(value)
    if not math.isfinite(n) or not lo <= n <= hi:
        raise ValueError(f"Valore fuori intervallo: {lo}–{hi}.")
    return n


def _full_name(person):
    return ' '.join(str(person.get(key) or '').strip() for key in ('first','surname')).strip() or 'Nome da aggiungere'


def _card_padding(size):
    return max(32.,32.*size/22)


def _name_width(people,size,font_type):
    """A bounded common measure: long names wrap instead of widening everyone."""
    scale=size/22
    widest=max((text_width(_full_name(p),size,font_type) for p in people),default=0)
    return math.ceil(min(320*scale,max(260*scale,widest+_card_padding(size))))


def name_lines(person, size=22, font_type='ui', width=None):
    """Wrap using actual font advances, without ellipses or dropping characters.

    Renderers should pass the shared card width; the old one-argument call
    remains valid with the normal 22-unit UI font.
    """
    size=finite(size,10,1000)
    width=_name_width([person],size,font_type) if width is None else float(width)
    available=max(size,width-_card_padding(size))
    result=[];line=''
    for word in _full_name(person).split():
        if line and text_width(line+' '+word,size,font_type)<=available+1e-7:
            line+=' '+word
            continue
        if line:result.append(line);line=''
        while text_width(word,size,font_type)>available+1e-7 and len(word)>1:
            low,high=1,len(word)
            while low<high:
                middle=(low+high+1)//2
                if text_width(word[:middle],size,font_type)<=available+1e-7:low=middle
                else:high=middle-1
            result.append(word[:low]);word=word[low:]
        line=word
    if line:result.append(line)
    return result or ['Nome da aggiungere']


def card_height(person, size=22, font_type='ui', width=None):
    size=finite(size,10,1000)
    date_space=size*.65+10 if person.get('years') else 0
    return math.ceil(24+sum((sum(vertical_metrics(line,font_type))+.12)*size
                            for line in name_lines(person,size,font_type,width))+date_space)


def card_size(state, size=22, font_type='ui'):
    """One compact width and height for every card in this composition."""
    size=finite(size,10,1000)
    people=state['people'] or [{'first':'','surname':''}]
    width=_name_width(people,size,font_type)
    name_height=max(sum((sum(vertical_metrics(line,font_type))+.12)*size
                        for line in name_lines(p,size,font_type,width)) for p in people)
    date_space=size*.65+10 if any(p.get('years') for p in people) else 0
    height=math.ceil(24+name_height+date_space)
    return width,height


def card_dimensions(person, size=22, font_type='ui', state=None):
    """Compatibility helper; pass state to obtain the shared composition size."""
    return card_size(state if state is not None else {'people':[person]},size,font_type)


def resize_positions(state, positions, settings=None):
    settings=settings or {}; size=finite(settings.get('font_size',22),10,1000)
    width,height=card_size(state,size,settings.get('font_type','ui'))
    if not positions:return {}
    first=next(iter(positions.values()))
    old_w=first.get('grid_w',first.get('w',W))
    old_h=first.get('grid_h',max(p.get('h',H) for p in positions.values()))
    same_font=first.get('text_size')==size and first.get('text_font','ui')==settings.get('font_type','ui')
    # Migrating old rectangles is a style change, not permission to move them.
    # A deliberate font change may scale free coordinates, but never a lock.
    keep_coordinates=same_font or 'text_size' not in first
    sx,sy=(1,1) if keep_coordinates else ((width+GAP)/(old_w+GAP),(height+GAP)/(old_h+GAP))
    x0=min(p['x'] for p in positions.values()); y0=min(p['y'] for p in positions.values())
    people={p['id']:p for p in state['people']}
    return {i:{**p,'x':p['x'] if p.get('locked') else x0+(p['x']-x0)*sx,
                    'y':p['y'] if p.get('locked') else y0+(p['y']-y0)*sy,
                    'w':width,'h':height, 'grid_w':width,'grid_h':height,
                    'text_size':size,'text_font':settings.get('font_type','ui')}
            for i,p in positions.items() if i in people}


def edges(state):
    return [(p, c, f["id"]) for f in state["families"]
            for p in f["parents"] for c in f["children"]]


def overlaps(a, b):
    return (a["x"] < b["x"]+b.get("w",W)+GAP and b["x"] < a["x"]+a.get("w",W)+GAP
            and a["y"] < b["y"]+b.get("h",H)+GAP and b["y"] < a["y"]+a.get("h",H)+GAP)


def arrange(state, positions, settings=None):
    from .layout import arrange_family
    return arrange_family(state,positions,settings)


def family_alignment(state,positions,identifier,horizontal=False):
    """Child center aligned to its parent junction (including two parents)."""
    axis,dim=('y','h') if horizontal else ('x','w')
    targets={'x':[],'y':[]}; own=positions[identifier]
    for family in state['families']:
        if identifier not in family['children']:continue
        parents=[positions[i] for i in family['parents'] if i in positions]
        if parents:
            targets[axis].append(sum(p[axis]+p[dim]/2 for p in parents)/len(parents)-own[dim]/2)
    return targets


def place(positions, identifier, x, y, locked=True, snap=True, extra_targets=None):
    pos = {**positions.get(identifier,{}), "x": finite(x, -100000, 100000), "y": finite(y, -100000, 100000), "locked": bool(locked)}
    if snap:
        candidates={'x':[],'y':[]}
        for i,q in positions.items():
            if i==identifier:continue
            for axis,dim in (('x','w'),('y','h')):
                candidates[axis].extend([q[axis],q[axis]+(q.get(dim,W if dim=='w' else H)-pos.get(dim,W if dim=='w' else H))/2])
        aligned=dict(pos)
        for axis in ('x','y'):
            priority=sorted((extra_targets or {}).get(axis,[]),key=lambda v:abs(v-pos[axis]))
            near=priority if priority and abs(priority[0]-pos[axis])<=18 else sorted(candidates[axis],key=lambda v:abs(v-pos[axis]))
            if near and abs(near[0]-pos[axis])<=18:aligned[axis]=near[0]
        if not any(k!=identifier and overlaps(aligned,q) for k,q in positions.items()):pos=aligned
    # Choose the nearest free slot around the drop, instead of repeatedly
    # pushing a card far to the right of the entire tree.
    others=[q for k,q in positions.items() if k!=identifier]
    if any(overlaps(pos,q) for q in others):
        xs={pos['x']};ys={pos['y']}
        for q in others:
            xs.update((q['x']-pos.get('w',W)-GAP,q['x']+q.get('w',W)+GAP))
            ys.update((q['y']-pos.get('h',H)-GAP,q['y']+q.get('h',H)+GAP))
        candidates=sorted(((x,y) for x in xs for y in ys),key=lambda q:((q[0]-pos['x'])**2+(q[1]-pos['y'])**2,q))
        for x,y in candidates:
            candidate={**pos,'x':x,'y':y}
            if not any(overlaps(candidate,q) for q in others):
                pos=candidate;break
    if pos["x"] > 200000:
        raise ValueError("Area di lavoro troppo estesa.")
    return {**positions, identifier: pos}


def bounds(positions):
    if not positions:
        return 0, 0, W, H
    x = min(v["x"] for v in positions.values())
    y = min(v["y"] for v in positions.values())
    # Include outside family rails, rounded junctions and their labels in print.
    return x-110, y-110, max(v["x"]+v.get("w",W) for v in positions.values())-x+220, max(v["y"]+v.get("h",H) for v in positions.values())-y+220


def sheet(config, positions):
    unit = config.get("unit", "mm")
    if unit not in ("mm", "cm"):
        raise ValueError("Scegli mm oppure cm.")
    factor = 10 if unit == "cm" else 1
    fmt = config.get("format", "A4")
    if fmt == "custom":
        width = finite(config.get("width", 125), 1, 5000)*factor
        height = finite(config.get("height", 256), 1, 5000)*factor
    elif fmt in ("A4", "A3"):
        width, height = (210, 297) if fmt == "A4" else (297, 420)
    else:
        raise ValueError("Formato sconosciuto.")
    if max(width, height) > 5000 or min(width, height) < 25:
        raise ValueError("Il foglio deve misurare fra 25 e 5000 mm.")
    orientation = config.get("orientation", "portrait")
    if orientation not in ("portrait", "landscape"):
        raise ValueError("Orientamento non valido.")
    if orientation == "landscape":
        width, height = height, width
    margin = finite(config.get("margin", 10), 0, 500)*factor
    safety = finite(config.get("safety", 3), 0, 100)*factor
    inset = margin+safety
    if width <= 2*inset or height <= 2*inset:
        raise ValueError("Margini e area di sicurezza occupano tutto il foglio.")
    x, y, bw, bh = bounds(positions)
    title_space=14 if str(config.get('title','')).strip() else 0
    available = (width-2*inset, height-2*inset-title_space)
    if min(available)<=0:raise ValueError('Il titolo e i margini occupano tutto il foglio.')
    mode = config.get("mode", "fit")
    if mode not in ("fit", "scale", "readable"):
        raise ValueError("Modalità scala non valida.")
    scale = min(available[0]/bw, available[1]/bh) if mode != "scale" else finite(config.get("scale", 100), 1, 1000)/100*25.4/96
    requested=finite(config.get('text_pt',0),0,1000)
    requested_scale=requested*25.4/(72*finite(config.get('font_size',22),10,1000))
    recommended_scale=max(scale,requested_scale)
    # Points are a physical size. Do not enlarge/shrink this mode to fill paper.
    if mode=='readable':scale=requested_scale if requested else 12*25.4/(72*finite(config.get('font_size',22),10,1000))
    return {"recommended_width":math.ceil(bw*recommended_scale+2*inset),"recommended_height":math.ceil(bh*recommended_scale+2*inset+title_space),"width": width, "height": height, "margin": margin, "safety": safety,
            "scale": scale, "tx": (width-bw*scale)/2-x*scale,
            "ty": title_space+(height-title_space-bh*scale)/2-y*scale,
            "overflow": bw*scale > available[0]+1e-6 or bh*scale > available[1]+1e-6,
            "font_pt": finite(config.get("font_size",22),10,1000)*scale*72/25.4}


FAMILY_COLORS = ['#226c59','#9b4d20','#405b9b','#883f78','#576d28','#276e85','#8a3f42','#61538d']


def family_color(family):
    import zlib
    value = family.get('gramps_id') or family['id']
    return FAMILY_COLORS[zlib.crc32(value.encode()) % len(FAMILY_COLORS)]


def rounded(points, radius=18):
    """Rounded orthogonal/polyline path, identical in canvas and PDF."""
    clean = [points[0]]
    for point in points[1:]:
        if point != clean[-1]:
            clean.append(point)
    # Collapse collinear points: aligned parents and children get straight stems.
    reduced=[]
    for p in clean:
        while len(reduced)>1 and abs((reduced[-1][0]-reduced[-2][0])*(p[1]-reduced[-1][1])-(reduced[-1][1]-reduced[-2][1])*(p[0]-reduced[-1][0]))<1e-8:
            reduced.pop()
        reduced.append(p)
    clean=reduced
    out = [f'M{clean[0][0]},{clean[0][1]}']
    for a,b,c in zip(clean,clean[1:],clean[2:]):
        ab, bc = math.dist(a,b), math.dist(b,c)
        r = min(radius,ab/2,bc/2)
        before = (b[0]+(a[0]-b[0])*r/ab,b[1]+(a[1]-b[1])*r/ab)
        after = (b[0]+(c[0]-b[0])*r/bc,b[1]+(c[1]-b[1])*r/bc)
        out.append(f'L{before[0]},{before[1]} Q{b[0]},{b[1]} {after[0]},{after[1]}')
    out.append(f'L{clean[-1][0]},{clean[-1][1]}')
    return ' '.join(out)


def connections(state, positions, settings=None):
    from .links import render_links
    return render_links(state,positions,settings)


def card_text(person, size=22, height=None, font_type='ui', width=None):
    size=finite(size,10,1000)
    name=' '.join(filter(None,[person['first'],person['surname']])) or 'Nome da aggiungere'
    width=width or card_dimensions(person,size,font_type)[0]
    lines=name_lines(person,size,font_type,width); height=height or card_height(person,size,font_type,width)
    out=[f'<title>{escape(name)}</title>']
    padding=12
    reserved=size*.65+10
    text_height=sum((sum(vertical_metrics(line,font_type))+.12)*size for line in lines)
    y=max(padding,(height-reserved-text_height)/2)
    for index,line in enumerate(lines):
        ascent,descent=vertical_metrics(line,font_type)
        y+=ascent*size
        if font_type!='ui':
            out.append(outlined(line,(width-text_width(line,size,font_type))/2,y,size,font_type))
        else:
            out.append(f'<text class="person-name" x="{width/2}" y="{y}" font-size="{size}" text-anchor="middle" font-weight="600">{escape(line)}</text>')
        y+=(descent+.12)*size
    if person.get('years'):
        date_size=max(12,size*.58)
        out.append(f'<text class="person-dates" x="{width/2}" y="{height-10}" font-size="{date_size}" text-anchor="middle" fill="#77736b">{escape(str(person["years"]))}</text>')
    return ''.join(out)


def drawing(state, positions, settings=None):
    settings=settings or {}; size=settings.get('font_size',22)
    out=[connections(state,positions,settings)]
    theme=settings.get('theme','screen')
    for p in state['people']:
        if p['id'] not in positions:continue
        q=positions[p['id']]; w,h=q['w'],q['h']
        text=card_text(p,size,h,settings.get('font_type','ui'),w)
        if theme=='screen':
            box=f'<rect width="{w}" height="{h}" rx="9" fill="white" stroke="#c9cdc1" stroke-width="1.2"/>'
        elif theme=='essential':
            box=f'<path d="M10,{h-2} H{w-10}" stroke="#aaa297" stroke-width="1"/>'
        else:
            box=f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="4" fill="{settings.get("paper_color","white")}" stroke="#b9afa0" stroke-width=".8"/>'
        out.append(f'<g transform="translate({q["x"]} {q["y"]})">{box}{text}</g>')
    return ''.join(out)


def print_settings(config, settings=None):
    theme=config.get('theme','classic'); font_type=config.get('font_type','classic')
    if theme not in ('classic','essential','heritage') or font_type not in ('classic','italic','script','ui'):
        raise ValueError('Stile di stampa non valido.')
    return {**(settings or {}),'font_size':finite(config.get('font_size',22),10,1000),
            'font_type':font_type,'theme':theme,'print_mode':True,
            'paper_color':'#fcf8ee' if theme=='heritage' else '#ffffff','ink':'#76664e' if theme=='heritage' else '#5d5a54'}


def prepare_print(state, positions, config, settings=None):
    style=print_settings(config,settings)
    composition=config.get('composition','as_seen')
    if composition not in ('as_seen','compact'):
        raise ValueError('Composizione di stampa non valida.')
    direction=config.get('direction') or style.get('direction','vertical')
    if direction not in ('auto','vertical','horizontal'):
        raise ValueError('Scegli sviluppo verticale oppure orizzontale.')
    directions=('vertical','horizontal') if direction=='auto' else (direction,)
    if composition=='compact':
        # Print reflow is a separate view: it never edits saved positions/locks.
        candidates=[]
        for chosen_direction in directions:
            for count in (2,3,4,6,8):
                for stagger in (True,False):
                    candidate_style={**style,'direction':chosen_direction,'siblings':count,'stagger':stagger}
                    candidate,_=arrange(state,{},candidate_style)
                    info=sheet({**config,'mode':'fit'},candidate)
                    _,_,w,h=bounds(candidate)
                    candidates.append((info['scale'],-w*h,-count,candidate,candidate_style))
        *_,positions,style=max(candidates,key=lambda item:item[:3])
    else:
        positions=resize_positions(state,positions,style)
    return positions,style


def svg(state, positions, config=None, guides=False, settings=None):
    if config is None:
        positions = resize_positions(state,positions,settings)
        x, y, w, h = bounds(positions)
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x-80} {y-80} {w+160} {h+160}" font-family="DejaVu Sans, sans-serif" fill="#203d33"><rect x="{x-80}" y="{y-80}" width="{w+160}" height="{h+160}" fill="#f8f9f3"/>{drawing(state, positions,settings)}</svg>'
    positions,settings = prepare_print(state,positions,config,settings)
    s = sheet(config, positions)
    settings={**settings,'physical_scale':s['scale']}
    w, h = s["width"], s["height"]
    guide = ''
    title=str(config.get('title','')).strip()[:120]
    ornament=''
    if title:
        title_size=min(8,(w-2*(s['margin']+s['safety']))/max(1,text_width(title,1,'classic')))
        title_w=text_width(title,title_size,'classic')
        ornament=outlined(title,(w-title_w)/2,s['margin']+s['safety']+title_size,title_size,'classic')
    if settings['theme']!='essential':
        inset=max(3,s['margin']*.5)
        ornament+=f'<rect x="{inset}" y="{inset}" width="{w-2*inset}" height="{h-2*inset}" fill="none" stroke="#b1a187" stroke-width=".3"/>'

    if guides:
        for inset, color in ((s["margin"], '#c37c30'), (s["margin"]+s["safety"], '#276653')):
            guide += f'<rect x="{inset}" y="{inset}" width="{w-2*inset}" height="{h-2*inset}" fill="none" stroke="{color}" stroke-width="0.3" stroke-dasharray="2 2"/>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}mm" height="{h}mm" viewBox="0 0 {w} {h}" font-family="DejaVu Sans, sans-serif" fill="#203d33"><defs><clipPath id="page"><rect width="{w}" height="{h}"/></clipPath></defs><rect width="100%" height="100%" fill="{settings["paper_color"]}"/>{ornament}<g clip-path="url(#page)"><g transform="translate({s["tx"]} {s["ty"]}) scale({s["scale"]})">{drawing(state, positions,settings)}</g></g>{guide}</svg>'


def pdf(state, positions, config, settings=None):
    # CairoSVG uses exactly the SVG paths, typography, physical dimensions and clip.
    import cairosvg
    return cairosvg.svg2pdf(bytestring=svg(state, positions, config,settings=settings).encode())
