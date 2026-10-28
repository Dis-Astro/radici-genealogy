"""Read-only family album, with physical typography on 150 x 100 mm pages."""
import io
import math
import zipfile
from html import escape
from .geometry import finite, family_color, rounded, svg
from .typography import width, vertical_metrics, outlined

PT=25.4/72
PAPER='#fffdf8'
INK='#302f2a'


def full_name(person):
    return ' '.join(str(person.get(key) or '').strip() for key in ('first','surname')).strip() or 'Nome da aggiungere'


def wrap(text,size,measure):
    lines=[];line=''
    for word in str(text).split():
        if line and width(line+' '+word,size,'classic')<=measure:line+=' '+word;continue
        if line:lines.append(line);line=''
        while width(word,size,'classic')>measure and len(word)>1:
            end=1
            while end<len(word) and width(word[:end+1],size,'classic')<=measure:end+=1
            lines.append(word[:end]);word=word[end:]
        line=word
    if line:lines.append(line)
    return lines or ['']


def numbers(pages):
    values=sorted(set(pages));result=[];index=0
    while index<len(values):
        last=index
        while last+1<len(values) and values[last+1]==values[last]+1:last+=1
        result.append(str(values[index]) if last==index else f'{values[index]}-{values[last]}')
        index=last+1
    return ', '.join(result)


def plan_album(state,config):
    if not state['people']:raise ValueError('Aggiungi almeno una persona prima di creare l’album.')
    size=finite(config.get('album_text_pt',12),12,72)
    people={p['id']:p for p in state['people']}
    name_size=size*PT;card_w=65.
    line_blocks={i:wrap(full_name(p),name_size,card_w-6) for i,p in people.items()}
    max_name=max(sum((sum(vertical_metrics(line,'classic'))+.18)*name_size for line in lines) for lines in line_blocks.values())
    # Reserve the same date and navigation rows in every card of this album.
    card_h=math.ceil((3.6+max_name+1.3+9*PT+9*PT)*2)/2
    rows=math.floor((60+5)/(card_h+5))
    if rows<2:
        raise ValueError('Questi nomi non entrano su 150 × 100 mm alla grandezza richiesta. Riduci i punti dei nomi; non vengono rimpiccioliti automaticamente.')
    capacity=min(4,(rows-1)*2)
    pages=[];groups=[];covered=set()
    for family in state['families']:
        parents=list(dict.fromkeys(i for i in family['parents'] if i in people))
        children=list(dict.fromkeys(i for i in family['children'] if i in people))
        if not parents and not children:continue
        if len(parents)>2:raise ValueError('Una famiglia contiene più di due genitori: controlla i legami prima di creare l’album.')
        if set(parents)&set(children):raise ValueError('Una persona risulta genitore e figlio nella stessa famiglia. Correggi il legame prima di creare l’album.')
        title=' e '.join(full_name(people[i]) for i in parents) or 'Genitori non registrati'
        chunks=[children[i:i+capacity] for i in range(0,len(children),capacity)] or [[]]
        group=dict(id=family['id'],title=title,pages=[])
        for index,chunk in enumerate(chunks):
            page=dict(kind='family',family=family,parents=parents,children=chunk,title=title,
                      part=index+1,parts=len(chunks),child_start=index*capacity+1,child_total=len(children))
            pages.append(page);group['pages'].append(page);covered.update(parents+chunk)
        groups.append(group)
    isolated=[i for i in people if i not in covered]
    if isolated:
        group=dict(id=None,title='Persone senza legami registrati',pages=[])
        for start in range(0,len(isolated),4):
            page=dict(kind='isolated',parents=[],children=isolated[start:start+4],title=group['title'])
            pages.append(page);group['pages'].append(page)
        groups.append(group)
    indexes=[];current=[];height=0
    for group in groups:
        row_height=len(wrap(group['title'],10.5*PT,112))*4+3.5
        if current and height+row_height>64:indexes.append(current);current=[];height=0
        current.append(group);height+=row_height
    if current:indexes.append(current)
    pages=[dict(kind='overview',title='Mappa d’insieme')]+[dict(kind='index',title='Le famiglie dell’album',groups=group) for group in indexes]+pages
    for number,page in enumerate(pages,1):page['number']=number
    return dict(state=state,people=people,pages=pages,groups=groups,text_pt=size,name_size=name_size,
                name_lines=line_blocks,card_w=card_w,card_h=card_h,
                title=str(config.get('album_title') or 'La storia della nostra famiglia').strip()[:120])


def text(value,x,y,size,align='left',font='classic',color=INK):
    if align=='center':x-=width(value,size,font)/2
    elif align=='right':x-=width(value,size,font)
    return outlined(value,x,y,size,font,color)


def header(plan,page):
    out=[f'<rect width="150" height="100" fill="{PAPER}"/>',
         '<rect x="3" y="3" width="144" height="94" rx="1" fill="none" stroke="#c6bdac" stroke-width=".22"/>']
    title=plan['title'] if page['kind']=='overview' else 'Le famiglie dell’album' if page['kind']=='index' else 'Un ricordo di famiglia'
    size=12*PT;lines=wrap(title,size,136)
    if len(lines)>2:size=9*PT;lines=wrap(title,size,136)
    for index,line in enumerate(lines):out.append(text(line,75,10+(index-(len(lines)-1)/2)*3.8,size,'center'))
    out.append('<path d="M7,16 H143" stroke="#c6bdac" stroke-width=".22"/>')
    out.append(text('Radici',7,94,9*PT,font='italic',color='#596451'))
    out.append(text(f'Pagina {page["number"]} di {len(plan["pages"])}',143,94,9*PT,'right',color='#596451'))
    return out


def reference(plan,page,identifier):
    current=page.get('family',{}).get('id');origins=[];families=[]
    for group in plan['groups']:
        if group['id']==current or not group['pages'] or group['pages'][0]['kind']!='family':continue
        family=group['pages'][0]['family'];target=[p['number'] for p in group['pages']]
        if identifier in family['children']:origins+=target
        if identifier in family['parents']:families+=target
    result=[]
    if origins:result.append('Origini p. '+numbers(origins))
    if families:result.append('Famiglia p. '+numbers(families))
    result=' · '.join(result)
    return result if width(result,9*PT,'classic')<=plan['card_w']-5 else 'Altri legami: vedi indice'


def card(plan,page,identifier,x,y):
    p=plan['people'][identifier];w,h=plan['card_w'],plan['card_h'];out=[]
    out.append(f'<g data-album-person="{escape(identifier,quote=True)}"><title>{escape(full_name(p))}</title><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="1.1" fill="#ffffff" stroke="#bcb5a6" stroke-width=".22"/>')
    baseline=y+1.8
    for line in plan['name_lines'][identifier]:
        up,down=vertical_metrics(line,'classic');baseline+=up*plan['name_size']
        out.append(text(line,x+w/2,baseline,plan['name_size'],'center'))
        baseline+=(down+.18)*plan['name_size']
    if p.get('years'):out.append(text(str(p['years']),x+w/2,y+h-5,9*PT,'center',color='#5d6058'))
    ref=reference(plan,page,identifier)
    if ref:out.append(text(ref,x+w/2,y+h-1.6,9*PT,'center',color='#3c6253'))
    out.append('</g>');return ''.join(out)


def page_svg(plan,page):
    out=header(plan,page);kind=page['kind']
    if kind=='overview':
        config=dict(format='custom',unit='mm',width=136,height=61,orientation='portrait',margin=0,safety=0,
                    font_size=22,mode='fit',theme='classic',font_type='classic',composition='compact',direction='auto')
        out.append(svg(plan['state'],{},config).replace('<svg ','<svg x="7" y="19" ',1))
        out.append(text('Mappa di orientamento: i nomi si leggono nelle schede successive.',75,86,9*PT,'center'))
    elif kind=='index':
        y=23
        for group in page['groups']:
            label=wrap(group['title'],10.5*PT,112)
            for line in label:out.append(text(line,9,y,10.5*PT));y+=4
            out.append(text('p. '+numbers(p['number'] for p in group['pages']),141,y-4,10.5*PT,'right',color='#3c6253'))
            out.append(f'<path d="M9,{y-2} H141" stroke="#e0dbcf" stroke-width=".15"/>');y+=3.5
    else:
        w,h=plan['card_w'],plan['card_h'];parents=page['parents'];children=page['children']
        locations={};y=22.;color=family_color(page['family']) if kind=='family' else '#748071'
        if parents:
            start=(150-(len(parents)*w+(len(parents)-1)*6))/2
            for col,i in enumerate(parents):locations[i]=(start+col*(w+6),y)
            if len(parents)==2:
                out.append(f'<path d="M{locations[parents[0]][0]+w},{y+h/2} H{locations[parents[1]][0]}" fill="none" stroke="{color}" stroke-width=".22"/>')
            y+=h+5
        child_rows=[children[i:i+2] for i in range(0,len(children),2)]
        for row in child_rows:
            start=(150-(len(row)*w+(len(row)-1)*6))/2
            for col,i in enumerate(row):locations[i]=(start+col*(w+6),y)
            y+=h+5
        if parents and children:
            stem_x=75.;start_y=22+h/2 if len(parents)==2 else 22+h
            last_y=max(locations[i][1]-2.5 for i in children)
            out.append(f'<path d="M{stem_x},{start_y} V{last_y}" fill="none" stroke="{color}" stroke-width=".22"/>')
            for i in children:
                x,cy=locations[i];center=x+w/2;bus=cy-2.5
                relation=page['family'].get('relations',{}).get(i,[6,6])
                present=[relation[page['family'].get('parent_roles',{}).get(p,index)] for index,p in enumerate(parents) if index<2]
                dash=' stroke-dasharray=".3 .7"' if 6 in present else ' stroke-dasharray="1.1 .7"' if 2 in present else ''
                path=rounded([(75,bus),(center,bus),(center,cy)],.7)
                out.append(f'<path data-child="{escape(i,quote=True)}" d="{path}" fill="none" stroke="{color}" stroke-width=".22"{dash}/>')
            for cy in sorted({locations[i][1] for i in children}):
                if sum(locations[i][1]==cy for i in children)>1 or cy!=max(locations[i][1] for i in children):
                    out.append(f'<circle cx="75" cy="{cy-2.5}" r=".4" fill="{color}"/>')
            if len(parents)==2:out.append(f'<circle cx="75" cy="{22+h/2}" r=".4" fill="{color}"/>')
        for identifier,(x,cy) in locations.items():out.append(card(plan,page,identifier,x,cy))
        if kind=='family':
            if not parents:note='Genitori non registrati: nessun legame viene supposto.'
            elif not children:note='Nessun figlio registrato per questa unione.'
            else:
                end=page['child_start']+len(children)-1
                note=f'Figli {page["child_start"]}-{end} di {page["child_total"]}'
                if page['parts']>1:
                    group=next(g for g in plan['groups'] if g['id']==page['family']['id'])
                    others=[p['number'] for p in group['pages'] if p is not page]
                    note+=' · Continua a p. '+numbers(others)
            out.append(text(note,75,85,9*PT,'center'))
            if children:out.append(text('Puntini: da confermare · Trattini: adottivo',75,89,8.5*PT,'center',color='#5d6058'))
        else:out.append(text('Queste persone sono conservate senza creare legami.',75,85,9*PT,'center'))
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="150mm" height="100mm" viewBox="0 0 150 100">'+''.join(out)+'</svg>'


def album(state,config,output):
    plan=plan_album(state,config)
    value=finite(config.get('album_page',1),1,len(plan['pages']))
    if not value.is_integer():raise ValueError('Scegli una pagina intera dell’album.')
    page=plan['pages'][int(value)-1]
    if output=='preview':
        return dict(svg=page_svg(plan,page),sheet=dict(width=150,height=100,font_pt=plan['text_pt'],people=len(state['people']),
                    page_people=len(set(page.get('parents',[])+page.get('children',[]))),direction='vertical',overflow=False,
                    album=True,page=page['number'],total_pages=len(plan['pages']),overview=page['kind']=='overview',
                    page_kind=page['kind'],routing_warning=False),
                    pages=[dict(number=p['number'],title=p['title'],kind=p['kind']) for p in plan['pages']])
    if output=='svgzip':
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
            for p in plan['pages']:archive.writestr(f'pagina-{p["number"]:03}.svg',page_svg(plan,p))
            archive.writestr('LEGGIMI.txt','Ogni pagina misura 150 x 100 mm. Stampare a dimensioni effettive / 100%, senza adattamento. La mappa iniziale orienta; i nomi leggibili sono nelle schede.\n')
        return stream.getvalue()
    if output=='pdf':
        import cairosvg
        from pypdf import PdfReader,PdfWriter
        writer=PdfWriter()
        for p in plan['pages']:
            content=cairosvg.svg2pdf(bytestring=page_svg(plan,p).encode())
            writer.add_page(PdfReader(io.BytesIO(content)).pages[0])
        writer.add_metadata({'/Title':plan['title'],'/Creator':'Radici - Album 150 x 100 mm'})
        stream=io.BytesIO();writer.write(stream);return stream.getvalue()
    raise ValueError('Per l’album scegli PDF oppure il pacchetto di pagine SVG.')
