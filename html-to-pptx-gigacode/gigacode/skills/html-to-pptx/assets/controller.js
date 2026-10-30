'use strict';
const frame=document.getElementById('preview');
const statusEl=document.getElementById('status');
const exportButton=document.getElementById('export');
const reportButton=document.getElementById('report');
let busy=false;
let lastReport=null;
const notices=[...PAYLOAD.warnings,
 'PPTX использует свои метрики шрифтов: переносы строк могут отличаться. Проверяйте результат в PowerPoint.',
 'Таблицы могут переноситься как отдельные редактируемые тексты и фигуры, а не единый объект «Таблица».',
 'SVG/рисунки и некоторые эффекты могут оставаться изображениями. Canvas и JS-графики без статического содержимого не поддерживаются.'];
document.getElementById('warnings').textContent=notices.join('\n');
function download(blob,name){const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),60000);}
function limit(promise,ms,label){let timer;return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error(label)),ms);})]).finally(()=>clearTimeout(timer));}
function dimensions(){const w=Number(document.getElementById('width').value),h=Number(document.getElementById('height').value);if(!Number.isInteger(w)||!Number.isInteger(h)||w<320||h<200||w>10000||h>10000)throw new Error('Некорректные размеры окна.');return{w,h};}
function resize(){if(busy)return;try{const{w,h}=dimensions();frame.style.width=w+'px';frame.style.height=h+'px';statusEl.textContent='Окно '+w+' × '+h+'. Проверьте внешний вид и нажмите «Скачать PPTX».';}catch(e){statusEl.textContent=e.message;}}
document.getElementById('width').value=PAYLOAD.width;document.getElementById('height').value=PAYLOAD.height;
document.getElementById('resize').onclick=resize;
reportButton.onclick=()=>download(new Blob([JSON.stringify(lastReport,null,2)],{type:'application/json'}),PAYLOAD.fileName.replace(/\.pptx$/i,'')+'.export-report.json');
frame.addEventListener('load',()=>{exportButton.disabled=false;resize();});
frame.srcdoc=PAYLOAD.document;
async function runExport(save=true){
 if(busy)throw new Error('Экспорт уже выполняется.');busy=true;exportButton.disabled=true;document.getElementById('resize').disabled=true;
 statusEl.textContent='Проверка ресурсов и экспорт…';
 const win=frame.contentWindow,doc=frame.contentDocument;
 lastReport={version:1,engine:'dom-to-pptx 2.1.2',viewport:dimensions(),warnings:[...notices],slides:[],status:'checking'};
 try{
  if(!win.domToPptx?.exportToPptx)throw new Error('Библиотека не загрузилась. Проверьте разрешение локальных скриптов.');
  await limit(doc.fonts.ready,15000,'Не завершилась загрузка шрифтов.');
  const slides=Array.from(doc.querySelectorAll('section.slide'));
  if(slides.length!==PAYLOAD.expectedSlides)throw new Error('Количество слайдов изменилось.');
  if(slides.some(s=>s.parentElement?.closest('section.slide')))throw new Error('Вложенные section.slide не поддерживаются.');
  await Promise.all(slides.flatMap(s=>Array.from(s.querySelectorAll('img'))).map(async img=>{
   if(!img.complete)await limit(new Promise((resolve,reject)=>{img.addEventListener('load',resolve,{once:true});img.addEventListener('error',()=>reject(new Error('Не загрузилось изображение.')),{once:true});}),15000,'Не загрузилось изображение.');
   if(!img.naturalWidth)throw new Error('Обнаружено пустое/недоступное изображение.');
  }));
  for(const [i,s] of slides.entries()){
   const r=s.getBoundingClientRect(),cs=win.getComputedStyle(s);
   if(r.width<1||r.height<1||cs.display==='none'||cs.visibility==='hidden'||Number(cs.opacity)===0)throw new Error('Слайд '+(i+1)+' скрыт или имеет нулевой размер. Подготовьте статический HTML со всеми видимыми слайдами.');
   if(cs.transform!=='none')throw new Error('Трансформация корня слайда '+(i+1)+' не поддерживается. Уберите масштабирование контейнера в копии исходника.');
   if(s.scrollHeight>s.clientHeight+3||s.scrollWidth>s.clientWidth+3)throw new Error('Слайд '+(i+1)+': содержимое выходит за рамку HTML. Увеличьте высоту/ширину контейнера в копии исходника до экспорта; автоматическое обрезание запрещено.');
   if(s.querySelector('canvas,video'))throw new Error('Слайд '+(i+1)+': canvas/video требуют статического изображения в исходном HTML.');
   lastReport.slides.push({number:i+1,width:r.width,height:r.height,text:s.innerText});
  }
  // Largest measured rectangle gives every original slide room; engine uses uniform contain scaling.
  const maxW=Math.max(...lastReport.slides.map(s=>s.width)),maxH=Math.max(...lastReport.slides.map(s=>s.height));
  const width=10,height=10*maxH/maxW;
  if(height<1||height>56)throw new Error('Слишком вытянутый формат слайдов для общей страницы PPTX.');
  lastReport.pageInches={width,height};
  // Pause CSS animations at their currently displayed state; restore afterwards.
  const animations=doc.getAnimations();const states=animations.map(a=>a.playState);animations.forEach(a=>a.pause());
  let blob;
  try{blob=await win.domToPptx.exportToPptx(slides,{fileName:PAYLOAD.fileName,width,height,skipDownload:true,autoEmbedFonts:false,svgAsVector:true});}
  finally{animations.forEach((a,i)=>{if(states[i]==='running')a.play();});}
  if(!blob||blob.size<1000)throw new Error('Получен пустой PPTX.');
  lastReport.status='exported';lastReport.bytes=blob.size;
  if(save)download(blob,PAYLOAD.fileName);
  statusEl.textContent='Готово: '+slides.length+' слайд(а/ов). Проверьте PPTX; отчёт доступен отдельной кнопкой.';
  document.getElementById('warnings').textContent=lastReport.warnings.join('\n');
  return blob;
 }catch(e){lastReport.status='failed';lastReport.error=String(e.message||e);statusEl.textContent='Экспорт остановлен: '+lastReport.error;throw e;}
 finally{busy=false;exportButton.disabled=false;reportButton.disabled=false;document.getElementById('resize').disabled=false;}
}
exportButton.onclick=()=>runExport().catch(()=>{});
// Test seam; no remote endpoint, server or automatic download.
window.localPptx={runExport,getReport:()=>lastReport};
