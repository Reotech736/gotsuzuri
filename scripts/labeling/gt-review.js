'use strict';
(async()=>{
 const $=id=>document.getElementById(id), canvas=$('photo'),ctx=canvas.getContext('2d'),ns='http://www.w3.org/2000/svg';
 const names={empty:'空',black:'黒',white:'白',unknown:'判別不能'};
 let views,view,photo,scale=1,tx=0,ty=0,selected=null,drag=null,generation=0;
 function fit(){if(!view)return;scale=Math.min(canvas.width/view.width,canvas.height/view.height);tx=(canvas.width-view.width*scale)/2;ty=(canvas.height-view.height*scale)/2;draw();}
 function draw(){ctx.clearRect(0,0,canvas.width,canvas.height);if(!photo)return;ctx.drawImage(photo,tx,ty,view.width*scale,view.height*scale);
  if($('overlay').checked)for(const s of view.sites){if(s.truth==='empty')continue;const x=tx+s.image[0]*view.width*scale,y=ty+s.image[1]*view.height*scale;ctx.strokeStyle=s.truth==='black'?'#f66':s.truth==='white'?'#7effe0':'#ffac42';ctx.lineWidth=2;ctx.beginPath();ctx.arc(x,y,6,0,Math.PI*2);ctx.stroke();}
  if(selected!==null){const s=view.sites[selected],x=tx+s.image[0]*view.width*scale,y=ty+s.image[1]*view.height*scale;ctx.strokeStyle='#ffe34d';ctx.lineWidth=3;ctx.strokeRect(x-12,y-12,24,24);}
 }
 function board(){const svg=$('board');svg.replaceChildren();const add=(tag,attrs,text)=>{const e=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;svg.append(e);};
  for(let n=0;n<19;n++){const p=35+n*390/18;add('line',{x1:35,y1:p,x2:425,y2:p,stroke:'#594326'});add('line',{x1:p,y1:35,x2:p,y2:425,stroke:'#594326'});add('text',{x:p,y:20,'text-anchor':'middle','font-size':11},n+1);add('text',{x:15,y:p+4,'font-size':11},n+1);}
  for(const s of view.sites){const x=35+(s.column-1)*390/18,y=35+(s.row-1)*390/18;if(s.truth==='black'||s.truth==='white')add('circle',{cx:x,cy:y,r:9,fill:s.truth==='black'?'#12161b':'#fff',stroke:'#55462f'});if(s.truth==='unknown'){add('circle',{cx:x,cy:y,r:9,fill:'#ffac42'});add('text',{x,y:y+5,'text-anchor':'middle','font-size':17},'×');}}
  if(selected!==null){const s=view.sites[selected];add('rect',{x:24+(s.column-1)*390/18,y:24+(s.row-1)*390/18,width:22,height:22,fill:'none',stroke:'#d12b27','stroke-width':2});}
 }
 function choose(i){selected=i;const s=view.sites[i];scale=Math.max(scale,Math.min(canvas.width,canvas.height)/(view.width/5));tx=canvas.width/2-s.image[0]*view.width*scale;ty=canvas.height/2-s.image[1]*view.height*scale;$('detail').textContent=`${s.row}行 ${s.column}列 · ${names[s.truth]}`;draw();board();}
 function loadImage(file,native=false){const current=++generation,img=new Image();$('status').textContent='写真を読み込み中…';img.onload=()=>{if(current!==generation)return;photo=img;$('status').textContent='読み取り専用 · 写真とGTを照合できます';$('resolution').textContent=native?'原寸PNGを使用中（画面では拡大縮小して表示）':'長辺2048以下のJPEGプレビュー。細部は原寸PNGで確認できます。';draw();};img.onerror=()=>{if(current===generation)$('status').textContent='写真を読み込めません。写真を選び直すか原寸PNGを開いてください。';};img.src=file;}
 function show(){view=views[Number($('dataset').value)];photo=null;selected=null;$('detail').textContent='図の交点をクリックすると写真の同じ交点を拡大します。';$('source').textContent=`${view.dataset} · 更新${view.revision} · ${view.role==='development'?'開発用':'最終確認用として留保'}`;$('counts').textContent=Object.entries(names).map(([k,v])=>`${v} ${view.counts[k]||0}`).join(' · ');$('original').href=view.original;board();fit();loadImage(view.preview);}
 $('dataset').onchange=show;for(const [id,delta]of[['prev',-1],['next',1]])$(id).onclick=()=>{$('dataset').value=(Number($('dataset').value)+delta+views.length)%views.length;show();};
 $('fit').onclick=fit;$('overlay').onchange=draw;$('native').onclick=()=>loadImage(view.original,true);
 function zoom(f,x=canvas.width/2,y=canvas.height/2){const next=Math.max(.02,Math.min(8,scale*f));tx=x-(x-tx)*next/scale;ty=y-(y-ty)*next/scale;scale=next;draw();}
 $('plus').onclick=()=>zoom(1.5);$('minus').onclick=()=>zoom(1/1.5);
 canvas.onwheel=e=>{e.preventDefault();const r=canvas.getBoundingClientRect();zoom(e.deltaY<0?1.15:1/1.15,e.clientX-r.left,e.clientY-r.top);};
 canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);};canvas.onpointermove=e=>{if(!drag)return;tx+=e.clientX-drag[0];ty+=e.clientY-drag[1];drag=[e.clientX,e.clientY];draw();};canvas.onpointerup=canvas.onpointercancel=()=>drag=null;
 $('board').onclick=e=>{const r=$('board').getBoundingClientRect(),x=(e.clientX-r.left)*460/r.width,y=(e.clientY-r.top)*460/r.height,c=Math.round((x-35)*18/390),row=Math.round((y-35)*18/390);if(c>=0&&c<19&&row>=0&&row<19)choose(row*19+c);};
 new ResizeObserver(()=>{const r=canvas.getBoundingClientRect();canvas.width=r.width;canvas.height=r.height;fit();}).observe(canvas);
 try{const response=await fetch('view-data.json');if(!response.ok)throw Error('HTTP '+response.status);({views}=await response.json());for(const [i,v]of views.entries()){const option=document.createElement('option');option.value=i;option.textContent=`${i+1}/${views.length} · ${v.dataset}`;$('dataset').append(option);}$('dataset').value=0;show();}catch(e){$('status').textContent='読み込めません：'+e.message;}
})();
