// Development only. No installation/download commands. Runtime export never uses this script.
// NODE_PATH=<existing modules> CHROMIUM_PATH=<existing executable> node tests/browser_test.cjs
const fs=require('fs'),os=require('os'),path=require('path'),assert=require('assert');
const {execFileSync}=require('child_process');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),tmp=fs.mkdtempSync(path.join(os.tmpdir(),'html-pptx-test-'));
const python=process.env.PYTHON||'python3';
const prepare=path.join(root,'.gigacode/skills/html-to-pptx/scripts/prepare.py');
const validate=path.join(root,'.gigacode/skills/html-to-pptx/scripts/validate_pptx.py');
(async()=>{
 if(!process.env.CHROMIUM_PATH)throw Error('Set CHROMIUM_PATH to an existing developer browser.');
 const output=path.join(tmp,'export.html');execFileSync(python,[prepare,path.join(root,'examples/demo.html'),'-o',output]);
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}});let requests=[];
  page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url())});
  await page.goto('file://'+output);await page.waitForFunction(()=>!document.getElementById('export').disabled);
  const geometry=await page.evaluate(()=>{const d=document.getElementById('preview').contentDocument;return Array.from(d.querySelectorAll('section.slide')).map(s=>{const r=s.getBoundingClientRect();return {w:r.width,h:r.height,text:s.innerText}})});
  assert.equal(geometry.length,2);assert.equal(geometry[0].w,1000);assert.equal(geometry[0].h,680);assert.equal(geometry[1].h,820);
  for(let n=0;n<2;n++){
   const data=await page.evaluate(async()=>Array.from(new Uint8Array(await (await localPptx.runExport(false)).arrayBuffer())));
   const pptx=path.join(tmp,'demo-'+n+'.pptx');fs.writeFileSync(pptx,Buffer.from(data));
   const report=JSON.parse(execFileSync(python,[validate,pptx,'--expected-slides','2'],{encoding:'utf8'}));
   assert(report.details.every(s=>s.editable_text_runs>10));
   for(let i=0;i<2;i++)assert.equal(report.details[i].text.replace(/\s/g,''),geometry[i].text.replace(/\s/g,''));
  }
  const downloaded=page.waitForEvent('download');
  await page.click('#export');
  const file=await downloaded;assert.equal(file.suggestedFilename(),'demo.pptx');await file.saveAs(path.join(tmp,'clicked.pptx'));
  execFileSync(python,[validate,path.join(tmp,'clicked.pptx'),'--expected-slides','2']);
  await page.waitForFunction(()=>!document.getElementById('export').disabled);
  assert.equal(requests.length,0);
  const hidden=await page.evaluate(async()=>{document.getElementById('preview').contentDocument.querySelector('section.slide').style.display='none';try{await localPptx.runExport(false);return false}catch(e){return /скрыт/.test(e.message)}});assert(hidden);
  const overflow=await page.evaluate(async()=>{const s=document.getElementById('preview').contentDocument.querySelector('section.slide');s.style.display='block';s.style.height='100px';try{await localPptx.runExport(false);return false}catch(e){return /рамку/.test(e.message)}});assert(overflow);
  console.log('PASS: two slides, dimensions, exact whitespace-normalized text, editable runs, repeat export, zero HTTP requests, hidden/overflow rejection.');
 }finally{await browser.close();fs.rmSync(tmp,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1});
