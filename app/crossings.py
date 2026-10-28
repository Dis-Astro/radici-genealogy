"""Explicit overpasses: a crossing of distinct unions never becomes a junction."""
import math


def simplify(points):
    result=[]
    for point in points:
        if result and point==result[-1]:continue
        while len(result)>1 and abs((result[-1][0]-result[-2][0])*(point[1]-result[-1][1])-(result[-1][1]-result[-2][1])*(point[0]-result[-1][0]))<1e-7:
            result.pop()
        result.append(point)
    return result


def overpasses(records, radius=6, clear=None):
    """Return bridges on straight spans, clear of rounded corners and cards.

    Each record has a family id and polyline. Same-family paths are actual
    branches and must not acquire crossing symbols. Work has a finite budget.
    """
    horizontals=[];verticals=[]
    for owner,record in enumerate(records):
        for a,b in zip(simplify(record['points']),simplify(record['points'])[1:]):
            if abs(a[1]-b[1])<1e-7 and abs(a[0]-b[0])>1e-7:
                horizontals.append((min(a[0],b[0]),max(a[0],b[0]),a[1],owner))
            elif abs(a[0]-b[0])<1e-7 and abs(a[1]-b[1])>1e-7:
                verticals.append((a[0],min(a[1],b[1]),max(a[1],b[1]),owner))
    found=[];seen=set();budget=250000
    for left,right,y,owner in horizontals:
        for x,top,bottom,other in verticals:
            budget-=1
            if budget<0:return found
            if records[owner]['family']==records[other]['family']:continue
            # Original corners are rounded with radius 12. Stay away from them.
            if not left+radius+12<x<right-radius-12 or not top+12<y<bottom-12:continue
            key=(round(x,4),round(y,4))
            if key in seen or any(math.dist((x,y),(item['x'],item['y']))<radius*3 for item in found):continue
            side=-1
            if clear:
                if not all(clear((px,py)) for px,py in ((x-radius,y),(x+radius,y),(x,y-radius*1.4))):
                    side=1
                    if not all(clear((px,py)) for px,py in ((x-radius,y),(x+radius,y),(x,y+radius*1.4))):continue
            found.append(dict(x=x,y=y,radius=radius,side=side,owner=owner));seen.add(key)
            if len(found)>=2000:return found
    return found


def bridge_svg(bridge,color,paper,stroke,halo):
    x,y,r,side=bridge['x'],bridge['y'],bridge['radius'],bridge['side']
    straight=f'M{x-r},{y} L{x+r},{y}'
    curve=f'M{x-r},{y} Q{x},{y+side*r*1.6} {x+r},{y}'
    return (f'<g class="connection-crossing" data-crossing="overpass"><title>Crocevia senza legame: la linea scavalca l’altra</title>'
            f'<path d="{straight}" fill="none" stroke="{paper}" stroke-width="{halo}"/>'
            f'<path d="{curve}" fill="none" stroke="{paper}" stroke-width="{halo}"/>'
            f'<path d="{curve}" fill="none" stroke="{color}" stroke-width="{stroke}" stroke-linecap="round"/></g>')
