#!/usr/bin/env python3
"""Prepare a self-contained, network-blocked HTML exporter. Python 3.9+, stdlib only."""
import argparse, base64, hashlib, html, json, mimetypes, re, secrets
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ASSETS = Path(__file__).resolve().parents[1] / 'assets'

class PreparationError(ValueError): pass

class Bundler:
    def __init__(self, root):
        self.root = root.resolve()
        self.warnings = []
        self.stack = set()
    def local(self, url, base):
        p = urlsplit(url)
        if p.scheme or p.netloc or url.startswith('//'):
            raise PreparationError('Внешний ресурс запрещён: ' + url)
        path = (base / unquote(p.path)).resolve()
        if not path.is_relative_to(self.root):
            raise PreparationError('Ресурс вне папки ресурсов: ' + str(path))
        if not path.is_file(): raise PreparationError('Ресурс не найден: ' + str(path))
        return path
    def data(self, url, base):
        if url.startswith('data:') or url.startswith('#'): return url
        path = self.local(url, base)
        mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        raw = path.read_bytes()
        if mime == 'image/svg+xml':
            s = raw.decode('utf-8-sig')
            if re.search(r'<script|<foreignObject|(?:href\s*=\s*[\"\'](?:https?:|//))', s, re.I):
                raise PreparationError('SVG со скриптом/внешней ссылкой не поддерживается: '+str(path))
        return 'data:' + mime + ';base64,' + base64.b64encode(raw).decode()
    def css(self, text, base):
        # CSS imports are expanded recursively, keeping the imported file's own base directory.
        def imp(m):
            path = self.local(m.group(1) or m.group(2), base)
            if path in self.stack: raise PreparationError('Циклический CSS @import: '+str(path))
            self.stack.add(path)
            out = self.css(path.read_text(encoding='utf-8-sig'), path.parent)
            self.stack.remove(path)
            media = m.group(3).strip()
            return ('@media '+media+'{'+out+'}') if media else out
        text = re.sub(r'@import\s+(?:url\(\s*[\"\']?([^\s\)\"\']+)[\"\']?\s*\)|[\"\']([^\"\']+)[\"\'])\s*([^;]*);', imp, text, flags=re.I)
        def url(m):
            raw = (m.group(1) or m.group(2) or m.group(3)).strip()
            return 'url("'+self.data(raw, base)+'")'
        return re.sub(r'url\(\s*(?:"([^"]*)"|\x27([^\x27]*)\x27|([^)]*))\s*\)', url, text, flags=re.I)

class Document(HTMLParser):
    def __init__(self, bundler, base):
        super().__init__(convert_charrefs=False)
        self.b, self.base, self.out = bundler, base, []
        self.skip = None
        self.style = False
        self.style_parts = []
        self.slides = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.skip: return
        if tag in ('script','iframe','object','embed'):
            self.b.warnings.append('Удалён активный элемент <'+tag+'>; динамическое содержимое не воспроизводится.')
            if tag not in ('embed',): self.skip = tag
            return
        if tag == 'base': raise PreparationError('<base> не поддерживается: используйте относительные локальные пути.')
        if tag == 'meta' and ('http-equiv' in a or a.get('charset')): return
        if tag == 'link':
            if 'stylesheet' in a.get('rel','').lower().split():
                path = self.b.local(a.get('href',''), self.base)
                css = self.b.css(path.read_text(encoding='utf-8-sig'), path.parent)
                self.out.append('<style>'+css+'</style>')
            return
        if tag == 'style': self.style = True; self.style_parts=[]; return
        if tag == 'section' and 'slide' in a.get('class','').split(): self.slides += 1
        clean=[]
        for key,val in attrs:
            if key.lower().startswith('on') or key in ('nonce','integrity','crossorigin','srcdoc','action','formaction'): continue
            if key == 'srcset':
                raise PreparationError('srcset не поддерживается: замените на один локальный src.')
            if key == 'style' and val: val=self.b.css(val,self.base)
            if key in ('src','poster') and val: val=self.b.data(val,self.base)
            if tag in ('image','use') and key in ('href','xlink:href') and val:
                val=self.b.data(val,self.base)
            if key == 'href' and val and val.lower().startswith(('javascript:','data:text/html')): continue
            clean.append(key if val is None else key+'="'+html.escape(val,quote=True)+'"')
        self.out.append('<'+tag+(' '+' '.join(clean) if clean else '')+'>')
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in ('img','meta','link','input','br','hr','source','embed'): self.handle_endtag(tag)
    def handle_endtag(self,tag):
        if self.skip:
            if tag == self.skip:self.skip=None
            return
        if tag == 'style' and self.style:
            self.out.append('<style>'+self.b.css(''.join(self.style_parts),self.base)+'</style>');self.style=False
        else:self.out.append('</'+tag+'>')
    def handle_data(self,data):
        if not self.skip:
            (self.style_parts if self.style else self.out).append(data)
    def handle_entityref(self,name): self.handle_data('&'+name+';')
    def handle_charref(self,name): self.handle_data('&#'+name+';')
    def handle_comment(self,data): pass
    def handle_decl(self,decl): pass

def prepare(source, output, root=None, width=1280, height=900):
    source,output=Path(source).resolve(),Path(output).resolve()
    if source==output: raise PreparationError('Нельзя перезаписывать исходный HTML.')
    if output.exists(): raise PreparationError('Выходной файл уже существует; выберите другое имя.')
    b=Bundler(Path(root) if root else source.parent)
    if not source.is_relative_to(b.root):raise PreparationError('HTML должен находиться внутри папки ресурсов.')
    p=Document(b,source.parent);p.feed(source.read_text(encoding='utf-8-sig'));p.close()
    if not p.slides:raise PreparationError('Не найдены section.slide.')
    nonce=secrets.token_hex(16)
    bundle=(ASSETS/'vendor/dom-to-pptx.bundle.js').read_text()
    manifest=json.loads((ASSETS/'vendor/manifest.json').read_text())
    if hashlib.sha256(bundle.encode()).hexdigest()!=manifest['sha256']:
        raise PreparationError('Контрольная сумма браузерной библиотеки не совпадает.')
    csp="default-src 'none'; script-src 'nonce-"+nonce+"'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; media-src data:; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'"
    prefix='<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="'+html.escape(csp,quote=True)+'">'
    doc=''.join(p.out)
    if re.search(r'<head(?:\s[^>]*)?>',doc,re.I):doc=re.sub(r'(<head(?:\s[^>]*)?>)',lambda m:m[0]+prefix,doc,count=1,flags=re.I)
    else:doc='<head>'+prefix+'</head>'+doc
    doc='<!doctype html>'+doc
    doc+='\n<script nonce="'+nonce+'">'+bundle.replace('</script','<\\/script')+'</script>'
    payload={'document':doc,'warnings':b.warnings,'fileName':source.stem+'.pptx','width':width,'height':height,'expectedSlides':p.slides}
    serialized=json.dumps(payload,ensure_ascii=True).replace('<','\\u003c')
    shell=(ASSETS/'shell.html').read_text()
    shell=shell.replace('/*__PAYLOAD__*/',serialized).replace('/*__CONTROLLER__*/',(ASSETS/'controller.js').read_text())
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(shell,encoding='utf-8')
    return {'output':str(output),'slides':p.slides,'warnings':b.warnings,'bytes':output.stat().st_size}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('html');ap.add_argument('-o','--output',required=True)
    ap.add_argument('--resource-root');ap.add_argument('--viewport-width',type=int,default=1280);ap.add_argument('--viewport-height',type=int,default=900)
    a=ap.parse_args()
    if not 320<=a.viewport_width<=10000 or not 200<=a.viewport_height<=10000:ap.error('Некорректный viewport.')
    try:print(json.dumps(prepare(a.html,a.output,a.resource_root,a.viewport_width,a.viewport_height),ensure_ascii=False,indent=2))
    except (PreparationError,OSError,UnicodeError) as e:ap.exit(2,'Ошибка: '+str(e)+'\n')
if __name__=='__main__':main()
