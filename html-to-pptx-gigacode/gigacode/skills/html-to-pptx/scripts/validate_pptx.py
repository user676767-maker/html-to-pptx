#!/usr/bin/env python3
"""Check PPTX ZIP/XML structure, slide count and editable texts; not a visual verifier."""
import argparse,json,re,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
NS={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
def validate(path,expected=None):
    with zipfile.ZipFile(path) as z:
        bad=z.testzip()
        if bad:raise ValueError('Повреждён ZIP: '+bad)
        names=sorted((n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)),key=lambda n:int(re.search(r'(\d+)\.xml',n)[1]))
        if not names:raise ValueError('Нет слайдов.')
        prs=ET.fromstring(z.read('ppt/presentation.xml'));size=prs.find('p:sldSz',NS)
        result={'slides':len(names),'page_emu':size.attrib,'details':[]}
        if expected is not None and len(names)!=expected:raise ValueError('Неверное количество слайдов.')
        for name in names:
            root=ET.fromstring(z.read(name));texts=[n.text or '' for n in root.findall('.//a:t',NS)]
            result['details'].append({'file':name,'editable_text_runs':len(texts),'pictures':len(root.findall('.//p:pic',NS)),'text':'\n'.join(texts)})
        return result
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('pptx');ap.add_argument('--expected-slides',type=int);ap.add_argument('--output');a=ap.parse_args()
    try:r=json.dumps(validate(a.pptx,a.expected_slides),ensure_ascii=False,indent=2)
    except (ValueError,KeyError,zipfile.BadZipFile,ET.ParseError,OSError) as e:ap.exit(2,str(e)+'\n')
    if a.output:Path(a.output).write_text(r,encoding='utf-8')
    else:print(r)
