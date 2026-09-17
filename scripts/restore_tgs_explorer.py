"""Restore focused 2D / exploded floors and render detail assets from the verified PDF."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess
import fitz
from PIL import Image

EXPECTED_PDF = '231244de5827b79da0af83f079a6f42c6b531695767bb5366c9a7d580729ccef'
VERSION = '2.2.0'

def path_data(items):
    commands=[]
    last=None
    def move(p):
        nonlocal last
        if last is None or abs(last[0]-p[0])+abs(last[1]-p[1])>.01:
            commands.append(f'M{p[0]:.2f},{p[1]:.2f}')
        last=p
    for item in items:
        if item[0]=='re':
            r=item[1]
            commands.append(f'M{r.x0:.2f},{r.y0:.2f}H{r.x1:.2f}V{r.y1:.2f}H{r.x0:.2f}Z')
            last=None
        elif item[0]=='l':
            move(item[1]);p=item[2]
            commands.append(f'L{p[0]:.2f},{p[1]:.2f}');last=p
        elif item[0]=='c':
            move(item[1]);commands.append('C'+','.join(f'{v:.2f}' for p in item[2:] for v in p));last=item[-1]
        elif item[0]=='qu':
            q=item[1];pts=[q.ul,q.ur,q.lr,q.ll];move(pts[0])
            for p in pts[1:]:commands.append(f'L{p[0]:.2f},{p[1]:.2f}')
            commands.append('Z');last=None
    return ''.join(commands)

def render_assets(data,site):
    if hashlib.sha256(data).hexdigest()!=EXPECTED_PDF:
        raise ValueError('Source PDF differs from the user-approved 2026-09-14 map')
    tiles=site/'tiles';tiles.mkdir(exist_ok=True)
    with fitz.open(stream=data,filetype='pdf') as doc:
        if len(doc)!=1:raise ValueError('Expected one map page')
        p=doc[0];w,h=p.rect.width,p.rect.height
        if abs(w-8503.94043)>.1 or abs(h-4960.62988)>.1:raise ValueError('Map coordinates changed')
        paths=[]
        # Keep source vector geometry; omit dark letter outlines from the overview.
        # The original detail tiles remain authoritative for all labels and fine features.
        for sh in p.get_drawings():
            fill=sh.get('fill');r=sh['rect']
            if fill is None or max(fill)<.45 or min(r.width,r.height)<5 or r.width*r.height<150:continue
            if max(fill)-min(fill)<.08 and max(fill)<.55:continue
            d=path_data(sh['items'])
            if not d:continue
            color='#'+''.join(f'{round(max(0,min(1,c))*255):02x}' for c in fill)
            rule='evenodd' if sh.get('even_odd') else 'nonzero'
            paths.append(f'<path d="{d}" fill="{color}" fill-rule="{rule}"/>')
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><rect width="100%" height="100%" fill="#eeeae5"/>'+''.join(paths)+'</svg>'
        (site/'overview.svg').write_text(svg,encoding='utf-8')
        dl=p.get_displaylist()
        count=0
        for j in range(math.ceil(h/512)):
            for i in range(math.ceil(w/512)):
                clip=fitz.Rect(i*512,j*512,min((i+1)*512,w),min((j+1)*512,h))
                pix=dl.get_pixmap(matrix=fitz.Matrix(3,3),colorspace=fitz.csRGB,alpha=False,clip=clip)
                image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
                image.save(tiles/f'{i}_{j}.webp','WEBP',quality=92,method=4)
                count+=1
    return {'detail_tiles':count,'overview_shapes':len(paths),'tile_scale':3}

def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser()
    parser.add_argument('--site',type=Path,default=root/'_site')
    parser.add_argument('--patch',type=Path,default=root/'tgs2026/explorer-enhancement.js')
    parser.add_argument('--pdf',type=Path)
    args=parser.parse_args();site=args.site
    patch=args.patch.read_text(encoding='utf-8')
    app=site/'app.js';text=app.read_text(encoding='utf-8').rstrip()
    if 'v2.2: restore scene-only' in text:raise RuntimeError('Enhancement already applied')
    if not text.endswith('})();'):raise RuntimeError('Unexpected application wrapper; refusing unsafe patch')
    # localStorage is optional; malformed prior state must not abort initialization.
    old="new Set(JSON.parse(localStorage.getItem('tgsVisited')||'[]'))"
    new="new Set((()=>{try{const v=JSON.parse(localStorage.getItem('tgsVisited')||'[]');return Array.isArray(v)?v:[]}catch(e){return[]}})())"
    if old not in text:raise RuntimeError('Expected state initialization changed')
    text=text.replace(old,new,1)
    text=text.replace("localStorage.setItem('tgsVisited',JSON.stringify([...S.visited]));","try{localStorage.setItem('tgsVisited',JSON.stringify([...S.visited]))}catch(e){toast('此环境无法保存已逛记录')};")
    app.write_text(text[:-5]+'\n'+patch+'\n})();\n',encoding='utf-8')
    subprocess.run(['node','--check',str(app)],check=True)
    index=site/'index.html';html=index.read_text(encoding='utf-8')
    html=html.replace('user-scalable=no','user-scalable=yes')
    html=html.replace('TGS 2026 精细巡馆地图</title>','TGS 2026 精细巡馆地图 v2.2</title>')
    html=html.replace('src="app.js"','src="app.js?v='+VERSION+'"')
    # Ensure a failed script reports a failure rather than an endless map spinner.
    bootstrap="<script>window.addEventListener('error',function(e){var b=document.querySelector('.loadbox');if(b&&!document.querySelector('#loading.hide'))b.textContent='地图启动失败：'+(e.message||'资源加载失败')});</script>"
    html=html.replace('<script>const B=',bootstrap+'<script>const B=')
    index.write_text(html,encoding='utf-8')
    if args.pdf:data=args.pdf.read_bytes()
    else:
        from build_tgs_pages import source_pdf
        data=source_pdf()
    report=render_assets(data,site)
    report['ui_version']=VERSION;report['script_sha256']=hashlib.sha256(app.read_bytes()).hexdigest()
    current=site/'build-report.json'
    previous=json.loads(current.read_text()) if current.exists() else {}
    previous.update(report);current.write_text(json.dumps(previous,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
