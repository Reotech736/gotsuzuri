'use strict';
(async () => {
  const $ = id => document.getElementById(id);
  $('status').textContent='保存済みの比較データを読み込み中…';
  const response = await fetch('view-data.json');
  if (!response.ok) throw new Error('比較データを読み込めません。');
  const data = await response.json();
  const names = {empty:'空', black:'黒', white:'白', unknown:'不明'};
  const reasons = {assigned:'割当済み', 'ambiguous-sites':'交点間で曖昧', 'candidate-collision':'候補が競合', 'outside-gate':'対応距離の範囲外', 'mixed-colors':'集約範囲に異色が混在'};
  const canvas = $('canvas'), ctx = canvas.getContext('2d');
  let view, photo, selection = null, scale = 1, tx = 0, ty = 0, width = 1, height = 1, loading = 0, drag = null;
  const options = ['sites','candidates','members','centers','errors','truth','corrected'];
  const label = ds => ds.startsWith('reference-top') ? '上方写真' : ds.startsWith('oblique-low') ? '低角度の写真' : ds.startsWith('oblique-high') ? '高い位置の写真' : ds;
  const xy = p => [tx + p[0]*view.width*scale, ty + p[1]*view.height*scale];
  const enabled = id => $(id).checked;
  const line = (a,b,color,dash=[]) => {
    if (!a || !b) return;
    ctx.strokeStyle=color; ctx.lineWidth=1.5; ctx.setLineDash(dash);
    ctx.beginPath();ctx.moveTo(...xy(a));ctx.lineTo(...xy(b));ctx.stroke();ctx.setLineDash([]);
  };
  function mark(p, color, shape, radius=5) {
    if (!p) return;
    const [x,y] = xy(p); ctx.strokeStyle=color;ctx.lineWidth=1.6;ctx.beginPath();
    if(shape==='square')ctx.rect(x-radius,y-radius,2*radius,2*radius);
    else if(shape==='diamond'){ctx.moveTo(x,y-radius);ctx.lineTo(x+radius,y);ctx.lineTo(x,y+radius);ctx.lineTo(x-radius,y);ctx.closePath();}
    else if(shape==='cross'){ctx.moveTo(x-radius,y);ctx.lineTo(x+radius,y);ctx.moveTo(x,y-radius);ctx.lineTo(x,y+radius);}
    else ctx.arc(x,y,radius,0,2*Math.PI);
    ctx.stroke();
  }
  function draw() {
    drawGT();
    ctx.clearRect(0,0,width,height);
    if (!photo || !view) return;
    ctx.drawImage(photo,tx,ty,view.width*scale,view.height*scale);
    for(const s of view.sites) {
      const [x,y]=xy(s.image);
      if(enabled('sites')){ctx.fillStyle='#46e2f5';ctx.fillRect(x-1,y-1,2,2);}
      if(enabled('truth') && ['black','white'].includes(s.truth)) {
        ctx.fillStyle=s.truth==='black'?'#000b':'#fffb';ctx.beginPath();ctx.arc(x,y,7,0,Math.PI*2);ctx.fill();mark(s.image,'#8afe93','circle',7);
      }
      if(enabled('errors')) {
        if(s.truth!=='unknown' && s.prediction==='unknown')mark(s.image,'#ffac42','circle',7);
        else if(s.truth!=='unknown' && s.truth!==s.prediction)mark(s.image,'#ff7070','square',8);
      }
    }
    for(const c of view.candidates) {
      const a=c.assignment, assigned=a.assignedIndex!==null, selected=selection?.kind==='candidate' && selection.id===c.id;
      if(enabled('members') && (!selection || selected || selection.kind!=='candidate')) {
        for(const m of c.members)if(m.image){const [x,y]=xy(m.image);ctx.fillStyle=m.state==='black'?'#ffbd55':'#b2fff9';ctx.fillRect(x-1.3,y-1.3,2.6,2.6);}
      }
      if(enabled('candidates')) {
        if(assigned)line(c.image,view.sites[a.assignedIndex].image,'#46e2f5');
        else if(selected)for(const alt of a.alternatives)line(c.image,view.sites[alt.index].image,'#ffac42',[5,4]);
        if(c.image){const [x,y]=xy(c.image);ctx.fillStyle=c.state==='black'?'#080a0e':'#fff';ctx.beginPath();ctx.arc(x,y,4,0,2*Math.PI);ctx.fill();mark(c.image,assigned?'#46e2f5':'#ffac42',assigned?'circle':'diamond',selected?9:6);}
      }
      if(enabled('corrected')){line(c.image,c.correctedImage,'#ff71c7',[3,4]);mark(c.correctedImage,'#ff71c7','square',4);}
    }
    if(enabled('centers'))for(const center of view.centers)mark(center.image,'#ff71c7','cross',9);
    if(selection){const selected=selection.kind==='site'?view.sites[selection.id]:view.candidates.find(c=>c.id===selection.id);if(selected)mark(selected.image,'#ffe34d','circle',13);}
  }
  function drawGT() {
    if(!view)return;
    const svg=$('gtBoard'), ns='http://www.w3.org/2000/svg', start=35, step=390/18;
    const elements=[];
    const add=(tag,attrs,text)=>{const el=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,String(v));if(text!==undefined)el.textContent=text;elements.push(el);return el;};
    const point=i=>[start+(i%19)*step,start+Math.floor(i/19)*step];
    for(let n=0;n<19;n++) {
      const p=start+n*step;
      add('line',{x1:start,y1:p,x2:425,y2:p,stroke:'#584123','stroke-width':1});
      add('line',{x1:p,y1:start,x2:p,y2:425,stroke:'#584123','stroke-width':1});
      add('text',{x:p,y:20,'text-anchor':'middle','font-size':10,fill:'#302719'},n+1);
      add('text',{x:17,y:p+3.5,'text-anchor':'middle','font-size':10,fill:'#302719'},n+1);
    }
    for(const r of [3,9,15])for(const c of [3,9,15])add('circle',{cx:start+c*step,cy:start+r*step,r:2.5,fill:'#584123'});
    for(const s of view.sites) {
      const [x,y]=point(s.index);
      if(['black','white'].includes(s.truth))add('circle',{cx:x,cy:y,r:9.5,fill:s.truth==='black'?'#141414':'#faf8ed',stroke:s.truth==='black'?'#000':'#75664f','stroke-width':1,class:'gt-stone','data-state':s.truth});
      else if(s.truth==='unknown')add('text',{x,y:y+5,'text-anchor':'middle','font-size':16,fill:'#923a00'},'?');
    }
    let selectedIndex=null, alternatives=[];
    if(selection?.kind==='site')selectedIndex=selection.id;
    else if(selection?.kind==='candidate') {
      const a=view.candidates.find(c=>c.id===selection.id).assignment;
      selectedIndex=a.assignedIndex;
      if(selectedIndex===null)alternatives=a.alternatives;
    }
    if(selectedIndex!==null){const [x,y]=point(selectedIndex);add('rect',{x:x-11,y:y-11,width:22,height:22,fill:'none',stroke:'#e33a24','stroke-width':3,class:'gt-selection'});}
    for(const a of alternatives){const [x,y]=point(a.index);add('circle',{cx:x,cy:y,r:11,fill:'none',stroke:'#d34d00','stroke-width':2,'stroke-dasharray':'3 2'});}
    const black=view.sites.filter(s=>s.truth==='black').length,white=view.sites.filter(s=>s.truth==='white').length;
    svg.setAttribute('aria-label',`GTの正解配置：黒${black}、白${white}。クリックまたは矢印キーで交点を選択`);
    svg.replaceChildren(...elements);
    $('gtSelection').textContent=selectedIndex!==null?`${Math.floor(selectedIndex/19)+1}行 ${selectedIndex%19+1}列：GT ${names[view.sites[selectedIndex].truth]}`:alternatives.length?'未割当：破線の輪は最近傍・次点の候補交点です。':`本人確認済み：黒${black}・白${white}。写真の隠れを復元した図ではありません。`;
  }
  function fit() {if(!view)return;scale=Math.min(width/view.width,height/view.height)*.96;tx=(width-view.width*scale)/2;ty=(height-view.height*scale)/2;draw();}
  function focus(points) {
    const xs=points.map(p=>p[0]*view.width),ys=points.map(p=>p[1]*view.height);
    const left=Math.min(...xs),right=Math.max(...xs),top=Math.min(...ys),bottom=Math.max(...ys);
    scale=Math.min(width/Math.max(120,right-left),height/Math.max(120,bottom-top))*.8;
    tx=width/2-(left+right)/2*scale;ty=height/2-(top+bottom)/2*scale;draw();
  }
  function zoom(factor, x=width/2, y=height/2) {
    const next=Math.max(.02,Math.min(8,scale*factor)); const ratio=next/scale;
    tx=x-(x-tx)*ratio;ty=y-(y-ty)*ratio;scale=next;draw();
  }
  function describe() {
    if(!selection){$('detail').textContent='写真の候補または交点を選んでください。';return;}
    if(selection.kind==='site') {
      const s=view.sites[selection.id];
      const cs=view.candidates.filter(c=>c.assignment.assignedIndex===s.index);
      $('detail').textContent=`${s.row}行 ${s.column}列\nGT：${names[s.truth]}\n現行：${names[s.baseline]} → PC試作：${names[s.prediction]}\n割当候補：${cs.length?cs.map(c=>'#'+c.id).join(', '):'なし'}\n割当なしは空の保証ではありません。`;
    } else {
      const c=view.candidates.find(c=>c.id===selection.id),a=c.assignment;
      const target=a.assignedIndex===null?'未割当':`${Math.floor(a.assignedIndex/19)+1}行 ${a.assignedIndex%19+1}列`;
      const alternative=a.alternatives.map(e=>`${Math.floor(e.index/19)+1}行${e.index%19+1}列（距離${e.distance.toFixed(3)}）`).join('\n');
      $('detail').textContent=`候補 #${c.id}：${names[c.state]}\n${reasons[a.reason]||a.reason} → ${target}\n色支持率：${(c.support*100).toFixed(1)}%（確率ではない）\n集約した支持点：${c.members.length}\n候補の連続盤面座標：(${c.x.toFixed(3)}, ${c.y.toFixed(3)})\n補正後：(${a.correctedBoardCenter.map(v=>v.toFixed(3)).join(', ')})${c.correctedImage?'':'／盤外のため仮想位置は非表示'}\n最近傍と次点：\n${alternative}\n座標は0始まりの列・行、距離は交点間隔単位。`;
    }
  }
  function select(kind,id,move=false) {
    selection={kind,id};describe();renderList();
    if(move) {
      const p=kind==='site'?view.sites[id].image:view.candidates.find(c=>c.id===id).image;
      const extent=.065;
      focus([[p[0]-extent,p[1]-extent],[p[0]+extent,p[1]+extent]]);
    } else draw();
  }
  function renderList() {
    const filter=$('filter').value;
    let entries;
    if(filter==='unassigned'||filter==='all')entries=view.candidates.filter(c=>filter==='all'||c.assignment.assignedIndex===null).map(c=>({kind:'candidate',id:c.id,text:`候補 #${c.id} ${names[c.state]}｜${reasons[c.assignment.reason]||c.assignment.reason}`}));
    else entries=view.sites.filter(s=>filter==='wrong'?s.truth!=='unknown'&&s.prediction!=='unknown'&&s.prediction!==s.truth:filter==='unknown'?s.prediction==='unknown':s.baseline!==s.prediction).map(s=>({kind:'site',id:s.index,text:`${s.row}行 ${s.column}列｜GT ${names[s.truth]}・現行 ${names[s.baseline]} → ${names[s.prediction]}`}));
    $('count').textContent=`${entries.length}件。選ぶとその周囲を拡大します。`;
    $('list').replaceChildren(...entries.map(e=>{const button=document.createElement('button');button.textContent=e.text;button.setAttribute('aria-pressed',String(selection?.kind===e.kind&&selection?.id===e.id));button.onclick=()=>select(e.kind,e.id,true);return button;}));
  }
  async function change() {
    const token=++loading;
    const preserveCamera=!!photo && view?.dataset===$('dataset').value;
    view=data.views.find(v=>v.dataset===$('dataset').value&&v.mode===$('mode').value);
    if(!preserveCamera)selection=null;
    photo=null;draw();$('status').textContent='画像を読み込み中…';
    const image=new Image();
    image.onload=()=>{if(token!==loading)return;photo=image;$('status').textContent='表示準備完了';if(preserveCamera)draw();else fit();};
    image.onerror=()=>{if(token===loading)$('status').textContent='画像を読み込めません。書き出しフォルダと画像を確認してください。';};
    image.src=data.previews[view.dataset];
    const assigned=view.candidates.filter(c=>c.assignment.assignedIndex!==null).length;
    $('summary').textContent=`正解 ${view.correct} ／ 誤り ${view.wrong} ／ 不明 ${view.unknown}\n`;
    const info=document.createElement('p');info.className='small';info.textContent=`現行 ${view.baseline.correct}／${view.baseline.wrong}／${view.baseline.unknown}。候補 ${view.candidates.length}、割当 ${assigned}、未割当 ${view.candidates.length-assigned}。GT更新${view.revision}。補正（列・行）= ${view.shift.map(v=>v.toFixed(3)).join(', ')}。`;$('summary').append(info);
    describe();renderList();
  }
  for(const ds of [...new Set(data.views.map(v=>v.dataset))]){const option=document.createElement('option');option.value=ds;option.textContent=label(ds);$('dataset').append(option);}
  $('dataset').value=data.views.find(v=>v.dataset.startsWith('oblique-low'))?.dataset||data.views[0].dataset;
  $('dataset').onchange=change;$('mode').onchange=change;$('filter').onchange=renderList;
  options.forEach(id=>$(id).onchange=draw);
  $('fit').onclick=fit;$('far').onclick=()=>focus(view.sites.filter(s=>s.row<=4&&s.column>=2&&s.column<=8).map(s=>s.image));
  $('zoomIn').onclick=()=>zoom(1.5);$('zoomOut').onclick=()=>zoom(1/1.5);
  $('gtBoard').onclick=e=>{
    const rect=$('gtBoard').getBoundingClientRect();
    const col=(e.clientX-rect.left)*460/rect.width, row=(e.clientY-rect.top)*460/rect.height;
    const c=Math.round((col-35)/(390/18)),r=Math.round((row-35)/(390/18));
    if(c>=0&&c<19&&r>=0&&r<19)select('site',r*19+c,true);
  };
  $('gtBoard').onkeydown=e=>{
    const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];
    if(!delta)return;e.preventDefault();
    let index=selection?.kind==='site'?selection.id:180;
    if(selection?.kind==='candidate')index=view.candidates.find(c=>c.id===selection.id).assignment.assignedIndex??180;
    const c=Math.max(0,Math.min(18,index%19+delta[0])),r=Math.max(0,Math.min(18,Math.floor(index/19)+delta[1]));
    select('site',r*19+c,true);
  };
  canvas.onwheel=e=>{e.preventDefault();const rect=canvas.getBoundingClientRect();zoom(e.deltaY<0?1.15:1/1.15,e.clientX-rect.left,e.clientY-rect.top);};
  canvas.onpointerdown=e=>{if(!photo)return;canvas.setPointerCapture(e.pointerId);drag={x:e.clientX,y:e.clientY,startX:e.clientX,startY:e.clientY};};
  canvas.onpointermove=e=>{if(!drag)return;tx+=e.clientX-drag.x;ty+=e.clientY-drag.y;drag.x=e.clientX;drag.y=e.clientY;draw();};
  canvas.onpointerup=e=>{
    if(!drag)return;const click=Math.hypot(e.clientX-drag.startX,e.clientY-drag.startY)<5;drag=null;if(!click)return;
    const rect=canvas.getBoundingClientRect(),p=[e.clientX-rect.left,e.clientY-rect.top];
    const choices=[];
    if(enabled('candidates'))for(const c of view.candidates){const q=xy(c.image);choices.push({kind:'candidate',id:c.id,d:Math.hypot(p[0]-q[0],p[1]-q[1])});}
    for(const s of view.sites){const q=xy(s.image);choices.push({kind:'site',id:s.index,d:Math.hypot(p[0]-q[0],p[1]-q[1])});}
    choices.sort((a,b)=>a.d-b.d);if(choices[0]?.d<18)select(choices[0].kind,choices[0].id);
  };
  canvas.onpointercancel=()=>{drag=null;};
  new ResizeObserver(()=>{const rect=canvas.getBoundingClientRect();width=rect.width;height=rect.height;const dpr=window.devicePixelRatio||1;canvas.width=width*dpr;canvas.height=height*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);if(view)fit();}).observe(canvas);
  change();
})().catch(error=>{document.getElementById('status').textContent=`表示できません：${error.message}`;});
