"""Quiet family links, with a short bridge between adjacent partners."""
import math
from html import escape


def render_links(state,positions,settings=None):
    from .geometry import rounded,family_color
    from .routing import Router
    settings=settings or {}; horizontal=settings.get('direction')=='horizontal'
    people={p['id']:p for p in state['people']}
    def point(u,v):return (v,u) if horizontal else (u,v)
    def uv(p):return (p['y'],p['x'],p['h'],p['w']) if horizontal else (p['x'],p['y'],p['w'],p['h'])
    def anchors(identifier,parent):
        u,v,w,h=uv(positions[identifier]); v+=h if parent else 0
        return point(u+w/2,v),point(u+w/2,v+(12 if parent else -12)),u+w/2,v
    def bridge(parents,probe):
        if len(parents)!=2:return None
        first,second=sorted((uv(positions[p]) for p,_ in parents))
        u,v,w,h=first; a,b,c,d=second; gap=a-u-w
        if abs(v-b)>.01 or abs(h-d)>.01 or not 16<=gap<=84:return None
        left,right=point(u+w,v+h/2),point(a,b+d/2)
        # Trim endpoints by 10px for the inflated obstacle check.
        if not probe.clear(point(u+w+10,v+h/2),point(a-10,b+d/2)):return None
        joint=point((u+w+a)/2,v+h/2)
        port=point((u+w+a)/2,v+h+12)
        if not probe.clear(joint,port):return None
        return left,right,joint,port
    probe=Router(positions);families=[];ports=[];hubs=[]
    for index,f in enumerate(state['families']):
        parents=[(p,anchors(p,True)) for p in f['parents'] if p in positions]
        children=[(c,anchors(c,False)) for c in f['children'] if c in positions]
        if not parents or (len(parents)<2 and not children):continue
        pair=bridge(parents,probe)
        mid=sum(a[2] for _,a in parents)/len(parents);end=max(a[3] for _,a in parents)
        first=min((a[3] for _,a in children),default=end+100)
        join=end+max(25,min(48,(first-end)/2));hub=point(mid,join)
        if pair and not children:hub=pair[2]
        elif not probe.free(hub):
            candidates=[point(mid,v+delta) for q in positions.values() for _,v,_,h in [uv(q)] for delta in (-12,h+12)]
            candidates=[p for p in candidates if probe.free(p)]
            if candidates:hub=min(candidates,key=lambda p:math.dist(p,hub))
        if any(math.dist(hub,p)<16 for p in hubs):
            candidates=[point(mid+du,join+dv) for dv in (0,32,-32,64,-64) for du in (0,48,-48,96,-96)]
            candidates=[p for p in candidates if probe.free(p) and all(math.dist(p,q)>=16 for q in hubs)]
            if candidates:hub=min(candidates,key=lambda p:math.dist(p,hub))
        hubs.append(hub);rail=None
        if len(children)>4 and max(a[3] for _,a in children)-min(a[3] for _,a in children)>40:
            relevant=[positions[i] for i,_ in parents+children]
            local_left=min(uv(p)[0] for p in relevant)-24
            hub_v=hub[0] if horizontal else hub[1]
            last_v=max(a[1][0] if horizontal else a[1][1] for _,a in children)
            candidates={mid,local_left,*[u+offset for q in positions.values() for u,_,w,_ in [uv(q)] for offset in (-24,w+24)]}
            candidates=[u for u in candidates if probe.clear(point(u,hub_v),point(u,last_v)) and probe.free(point(u,hub_v))]
            rail_u=min(candidates,key=lambda u:(abs(u-mid),u)) if candidates else local_left
            start,end_point=point(rail_u,hub_v),point(rail_u,last_v)
            branches={c:point(rail_u,a[1][0] if horizontal else a[1][1]) for c,a in children}
            rail=(start,end_point,branches);ports.extend([start,end_point,*branches.values()])
        families.append((f,parents,children,hub,rail,pair))
        ports.append(hub);ports.extend(a[1] for _,a in parents+children)
        if pair:ports.extend(pair[2:])
    router=Router(positions,ports);out=[];records=[]
    physical=settings.get('physical_scale')
    stroke=.55*25.4/72/physical if physical else 1.8
    halo=stroke+3.2 if not physical else stroke*2.8
    for f,parents,children,hub,rail,pair in families:
        color=settings.get('ink') or family_color(f);paths=[]
        if pair:
            left,right,joint,port=pair;paths.append(([left,right],'','couple-stem'))
            if children:paths.append(([joint]+router.route(port,hub),'',''))
        else:
            for _,(anchor,port,_,_) in parents:paths.append(([anchor]+router.route(port,hub),'',''))
        if rail:
            start,end_point,branches=rail;paths.append((router.route(hub,end_point,[hub,start,end_point]),'',''))
        for child,(anchor,port,_,_) in children:
            relations=f.get('relations',{}).get(child,[6,6])
            present=[relations[f.get('parent_roles',{}).get(p,index)] for index,p in enumerate(f['parents']) if index<2]
            dash='3 6' if 6 in present else '9 5' if 2 in present else ''
            paths.append((router.route(rail[2][child] if rail else hub,port)+[anchor],dash,''))
        names=[' '.join(filter(None,(people.get(p,{}).get('first'),people.get(p,{}).get('surname')))) for p,_ in parents]
        title=escape(' e '.join(filter(None,names)))
        fid=escape(f['id'],quote=True);record=escape(f.get('gramps_id',''),quote=True)
        out.append(f'<g class="family-link" data-family="{fid}" data-record="{record}" fill="none" stroke-linecap="round" stroke-linejoin="round"><title>{title} · {len(children)} figli visibili</title>')
        rendered=[(rounded(points,12),dash,kind) for points,dash,kind in paths]
        for path,_,_ in rendered:out.append(f'<path class="connection-halo" d="{path}" stroke="{settings.get("paper_color","#fbfaf7")}" stroke-width="{halo}"/>')
        for path,dash,kind in rendered:
            out.append(f'<path class="family-stem" data-kind="{kind or "descent"}" d="{path}" stroke="{color}" stroke-width="{stroke}"'+(f' stroke-dasharray="{dash}"' if dash else '')+'/>')
        if children or not pair:
            x,y=hub;out.append(f'<circle class="family-junction" cx="{x}" cy="{y}" r="2.2" fill="{color}"/>')
        for points,dash,kind in paths:records.append(dict(family=f['id'],points=points,color=color,dash=dash))
        # Actual branch points on the wrapped child bus, including a pair's T.
        junctions=[]
        if pair and children:junctions.append(pair[2])
        if rail:
            for point in set(rail[2].values()):
                count=sum(p==point for p in rail[2].values())
                if point not in rail[:2] or count>1:junctions.append(point)
        if junctions:
            dots=''.join(f'<circle class="family-junction" cx="{x}" cy="{y}" r="2.2" fill="{color}"/>' for x,y in junctions)
            out.append(dots)
        out.append('</g>')
    from .crossings import overpasses,bridge_svg
    radius=max(5.,.8/physical) if physical else 6.
    for crossing in overpasses(records,radius,probe.free):
        record=records[crossing['owner']]
        out.append(f'<g class="family-overlay" data-family="{escape(record["family"],quote=True)}">'+bridge_svg(crossing,record['color'],settings.get('paper_color','#fbfaf7'),stroke,halo)+'</g>')
    if router.failures:out.insert(0,'<g data-routing-warning="true"><title>Alcuni percorsi richiedono una ricomposizione o la stampa di un ramo.</title></g>')
    return ''.join(out)
