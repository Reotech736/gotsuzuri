"use strict";
const $ = id => document.getElementById(id);
const names = {empty: "空", black: "黒", white: "白", unknown: "判別不能"};
const canvas = $("board"), ctx = canvas.getContext("2d");
const detail = $("detail"), dctx = detail.getContext("2d");
const photo = new Image();
let data, token, selected = 0, aligning = true, dragging = -1;
let history = [], dirty = false, saving = false, saveTimer, saveFailed = false;

function point(column, row) {
    const [[x0,y0],[x1,y1],[x2,y2],[x3,y3]] = data.corners;
    const dx1=x1-x2, dx2=x3-x2, dx3=x0-x1+x2-x3;
    const dy1=y1-y2, dy2=y3-y2, dy3=y0-y1+y2-y3;
    let g=0, h=0;
    if (Math.abs(dx3)>1e-10 || Math.abs(dy3)>1e-10) {
        const det=dx1*dy2-dx2*dy1;
        if (Math.abs(det)<1e-10) return null;
        g=(dx3*dy2-dx2*dy3)/det; h=(dx1*dy3-dx3*dy1)/det;
    }
    const u=column/18, v=row/18, den=g*u+h*v+1;
    if (den<=1e-10) return null;
    return [((x1-x0+g*x1)*u+(x3-x0+h*x3)*v+x0)/den*data.width,
        ((y1-y0+g*y1)*u+(y3-y0+h*y3)*v+y0)/den*data.height];
}

function validGeometry() {
    if(!Array.isArray(data.corners)||data.corners.length!==4||data.corners.some(p=>
        !Array.isArray(p)||p.length!==2||p.some(v=>typeof v!=="number"||!Number.isFinite(v)||v<0||v>1)))return false;
    for (let i=0;i<4;i++) {
        const a=data.corners[i],b=data.corners[(i+1)%4],c=data.corners[(i+2)%4];
        if ((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0])<=1e-8) return false;
    }
    return [[0,0],[18,0],[18,18],[0,18]].every(p=>point(...p));
}

function remember() { history.push(structuredClone(data)); if(history.length>100) history.shift(); }
function askConfirmation(message) {
    const dialog=$("confirmation");$("confirmationText").textContent=message;
    return new Promise(resolve=>{
        const finish=accepted=>{dialog.close();resolve(accepted);};
        $("confirmationCancel").onclick=()=>finish(false);
        $("confirmationAccept").onclick=()=>finish(true);
        dialog.oncancel=event=>{event.preventDefault();finish(false);};
        dialog.showModal();
    });
}
function changed() { data.reviewCompleted=false; scheduleSave(); render(); }
function status(text, kind="") { $("saveStatus").textContent=text; $("saveStatus").className=kind; }
function scheduleSave() {
    dirty=true; status("未保存の変更があります…", "pending");
    clearTimeout(saveTimer); saveTimer=setTimeout(save,180);
}
async function save() {
    if (saving || !dirty || saveFailed) return;
    saving=true;
    try {
        while(dirty) {
            dirty=false;
            const snapshot=structuredClone(data);
            status("PCへ保存中…", "pending");
            const response=await fetch("/api/save", {method:"POST",headers:{"Content-Type":"application/json","X-Label-Token":token},
                body:JSON.stringify({expectedRevision:data.revision,data:snapshot})});
            const result=await response.json();
            if(!response.ok) throw new Error(result.error || "保存できませんでした");
            data.revision=result.revision; data.savedAt=result.savedAt;
        }
        status("PCに保存済み · "+new Date(data.savedAt).toLocaleTimeString("ja-JP"));
        $("retrySave").hidden=true;
    } catch(error) {
        dirty=true; saveFailed=true; $("retrySave").hidden=false;
        status("保存失敗："+error.message, "error");
    } finally { saving=false; }
}
$("retrySave").onclick=()=>{saveFailed=false;save();};
window.addEventListener("beforeunload",event=>{if(dirty||saving){event.preventDefault();event.returnValue="";}});

function circle(context,x,y,r,fill,stroke,width) {
    context.beginPath();context.arc(x,y,r,0,Math.PI*2);
    if(fill){context.fillStyle=fill;context.fill();}
    if(stroke){context.strokeStyle=stroke;context.lineWidth=width;context.stroke();}
}
function render() {
    if(!data || !photo.complete || !photo.naturalWidth) return;
    drawCornerLoupe();
    ctx.clearRect(0,0,canvas.width,canvas.height); ctx.drawImage(photo,0,0);
    const scale=canvas.width / Math.max(1,canvas.getBoundingClientRect().width);
    const valid=validGeometry();
    if(valid && $("showGrid").checked) {
        for(let i=0;i<361;i++) {
            const p=point(i%19,Math.floor(i/19)), label=data.labels[i];
            if(label===null) circle(ctx,...p,2.1*scale,"#30c8ca99","#102e2866",.6*scale);
            if(label==="empty") circle(ctx,...p,2.4*scale,"#49b77c","#173d2b",.6*scale);
            if(label==="black") circle(ctx,...p,4.4*scale,"#131719","#fff",1.2*scale);
            if(label==="white") circle(ctx,...p,4.4*scale,"#fff","#111",1.2*scale);
            if(label==="unknown") circle(ctx,...p,4.4*scale,null,"#ec982c",1.8*scale);
        }
    }
    if(valid) {
        const p=point(selected%19,Math.floor(selected/19));
        circle(ctx,...p,9*scale,null,"#d42979",2*scale);
        drawDetail(p);
    }
    if(aligning) data.corners.forEach((p,i)=>{
        const x=p[0]*data.width,y=p[1]*data.height;
        circle(ctx,x,y,12*scale,"#ffd34a","#182e21",1.5*scale);
        ctx.font=`bold ${13*scale}px sans-serif`;ctx.textAlign="center";ctx.textBaseline="middle";ctx.fillStyle="#182e21";ctx.fillText(i+1,x,y);
    });
    const counts={empty:0,black:0,white:0,unknown:0};let missing=0;
    data.labels.forEach(v=>v===null?missing++:counts[v]++);
    $("datasetName").textContent=data.datasetId;
    $("progress").textContent=`分類済み ${361-missing} / 361`;
    $("progressBar").value=361-missing;
    $("counts").textContent=`空 ${counts.empty} · 黒 ${counts.black} · 白 ${counts.white} · 判別不能 ${counts.unknown} · 未分類 ${missing}`;
    $("selection").textContent=`${Math.floor(selected/19)+1}行 · ${selected%19+1}列`;
    $("currentLabel").textContent=data.labels[selected]===null?"未分類":names[data.labels[selected]];
    $("confirmGeometry").hidden=!aligning;
    $("confirmGeometry").disabled=!valid;
    $("alignMode").hidden=aligning;
    $("instruction").textContent=aligning ? (valid?"①左上→②右上→③右下→④左下。必要なら丸をドラッグし、交点の重なりを確認します。":"四隅が交差・重複しています。丸を移動してください。"):
        "写真の交点をクリックして選択し、右の画像を見て空・黒・白・判別不能を記録します。";
    document.querySelectorAll("[data-label]").forEach(b=>{
        b.disabled=aligning;b.classList.toggle("active",data.labels[selected]===b.dataset.label);
    });
    $("fillEmpty").disabled=aligning;$("clear").disabled=aligning;$("undo").disabled=!history.length;
    $("referencePanel").hidden=!data.referenceDraft;
    $("labelMeaning").textContent=data.referenceApplied?"参考GTで実配置が分かる点はそのラベルを保ちます。実配置自体を確認できない点は判別不能です。写真での見えにくさは別の問題です。":"「判別不能」は写真から決められない場合です。「空」とは別に記録します。";
    $("applyReference").disabled=aligning||data.labels.some(v=>v!==null);
    $("referenceStatus").textContent=data.referenceDraft ? `${data.referenceDraft.datasetId} · 更新 ${data.referenceDraft.annotationRevision} · ${data.referenceApplied?"下書き適用済み。盤全体の確認は別途必要です。":"位置合わせ確認後、未分類の状態で適用できます。"}` : "";
    $("finish").disabled=aligning||missing>0||data.reviewCompleted;
    $("completion").textContent=data.reviewCompleted?"本人の確認完了として保存しています。":
        (missing===0&&!aligning?"全交点にラベルがあります。盤全体を見直してから確認完了にしてください。":"");
}

function drawCornerLoupe() {
    const loupe=$("cornerLoupe");
    loupe.hidden=!aligning||dragging<0;
    if(loupe.hidden)return;
    const image=$("loupeImage"),context=image.getContext("2d"),rect=canvas.getBoundingClientRect();
    const p=data.corners[dragging],zoom=3*rect.width/data.width;
    context.setTransform(1,0,0,1,0,0);context.fillStyle="#17251d";context.fillRect(0,0,image.width,image.height);
    context.save();context.translate(image.width/2,image.height/2);context.scale(zoom,zoom);
    context.imageSmoothingEnabled=true;context.drawImage(photo,-p[0]*data.width,-p[1]*data.height);context.restore();
    for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]) {
        context.beginPath();context.moveTo(120+dx*4,90+dy*4);context.lineTo(120+dx*17,90+dy*17);
        context.strokeStyle="#111";context.lineWidth=4;context.stroke();
        context.strokeStyle="#ffd34a";context.lineWidth=2;context.stroke();
    }
    $("loupeTitle").textContent=`${dragging+1}の調整 · 表示の3倍（十字の中心が指定位置）`;
    const x=rect.left+p[0]*rect.width,y=rect.top+p[1]*rect.height;
    const height=loupe.offsetHeight,width=loupe.offsetWidth;
    loupe.style.left=`${Math.max(4,Math.min(innerWidth-width-4,x-width/2))}px`;
    const top=y-height-28>=4?y-height-28:y+28;
    loupe.style.top=`${Math.max(4,Math.min(innerHeight-height-4,top))}px`;
}

function drawDetail(center) {
    // 近隣交点を含む範囲を元画像から直接切り出す。モデル用の固定サイズ画像はまだ作らない。
    const c=selected%19,r=Math.floor(selected/19), neighbors=[];
    for(const dx of [-1.25,1.25]) for(const dy of [-1.25,1.25]) {
        const p=point(Math.max(0,Math.min(18,c+dx)),Math.max(0,Math.min(18,r+dy)));
        if(p)neighbors.push(p);
    }
    const radius=Math.max(16,...neighbors.map(p=>Math.hypot(p[0]-center[0],p[1]-center[1])));
    const left=Math.max(0,Math.floor(center[0]-radius)),top=Math.max(0,Math.floor(center[1]-radius));
    const right=Math.min(data.width,Math.ceil(center[0]+radius)),bottom=Math.min(data.height,Math.ceil(center[1]+radius));
    const w=right-left,h=bottom-top,zoom=Math.min(detail.width/w,detail.height/h);
    const dw=w*zoom,dh=h*zoom,ox=(detail.width-dw)/2,oy=(detail.height-dh)/2;
    dctx.fillStyle="#17251d";dctx.fillRect(0,0,detail.width,detail.height);
    dctx.imageSmoothingEnabled=zoom<1;dctx.drawImage(photo,left,top,w,h,ox,oy,dw,dh);
    const x=ox+(center[0]-left)*zoom,y=oy+(center[1]-top)*zoom;
    for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]) {
        dctx.beginPath();dctx.moveTo(x+dx*4,y+dy*4);dctx.lineTo(x+dx*16,y+dy*16);
        dctx.strokeStyle="#111";dctx.lineWidth=3;dctx.stroke();
        dctx.strokeStyle="#ff4aa0";dctx.lineWidth=1.5;dctx.stroke();
    }
    $("cropInfo").textContent=`元画像の ${w}×${h}px を表示（${zoom.toFixed(1)}倍）。十字は盤面交点です。石がずれて見える場合もあります。`;
}

function eventPosition(event) {
    const rect=canvas.getBoundingClientRect();
    return [(event.clientX-rect.left)/rect.width,(event.clientY-rect.top)/rect.height];
}
canvas.onpointerdown=event=>{
    const p=eventPosition(event);
    if(aligning) {
        let best=Infinity;
        data.corners.forEach((corner,i)=>{
            const d=Math.hypot((p[0]-corner[0])*canvas.clientWidth,(p[1]-corner[1])*canvas.clientHeight);
            if(d<24 && d<best){best=d;dragging=i;}
        });
        if(dragging>=0){remember();canvas.setPointerCapture(event.pointerId);render();}
    } else if(validGeometry()) {
        let best=Infinity;
        for(let i=0;i<361;i++) {
            const q=point(i%19,Math.floor(i/19)),d=Math.hypot((p[0]-q[0]/data.width)*canvas.clientWidth,(p[1]-q[1]/data.height)*canvas.clientHeight);
            if(d<best){best=d;selected=i;}
        }
        render();
    }
};
canvas.onpointermove=event=>{
    if(dragging<0)return;
    data.corners[dragging]=eventPosition(event).map(v=>Math.max(0,Math.min(1,v)));render();
};
function endDrag() {if(dragging>=0){dragging=-1;if(validGeometry())scheduleSave();render();}}
canvas.onpointerup=endDrag;canvas.onpointercancel=endDrag;
$("confirmGeometry").onclick=()=>{if(!validGeometry())return;remember();data.geometryReviewed=true;aligning=false;changed();};
$("alignMode").onclick=async()=>{
    if(data.labels.some(v=>v!==null)&&!await askConfirmation("四隅をやり直すと全ラベルを未分類へ戻します。必要なら先にJSONをダウンロードしてください。続けますか？"))return;
    remember();data.labels=Array(361).fill(null);data.geometryReviewed=false;if(data.referenceDraft)data.referenceApplied=false;aligning=true;changed();
};
$("showGrid").onchange=render;
function assign(label) {
    if(aligning)return;
    remember();data.labels[selected]=label;
    if($("autoAdvance").checked)advanceMissing();
    changed();
}
function advanceMissing() {
    for(let offset=1;offset<=361;offset++) {const i=(selected+offset)%361;if(data.labels[i]===null){selected=i;return;}}
}
document.querySelectorAll("[data-label]").forEach(button=>button.onclick=()=>assign(button.dataset.label));
$("clear").onclick=()=>assign(null);
$("previous").onclick=()=>{selected=(selected+360)%361;render();};
$("next").onclick=()=>{selected=(selected+1)%361;render();};
$("nextMissing").onclick=()=>{advanceMissing();render();};
$("undo").onclick=()=>{
    if(!history.length)return;
    const revision=data.revision,savedAt=data.savedAt;
    data=history.pop();data.revision=revision;data.savedAt=savedAt;aligning=!data.geometryReviewed;scheduleSave();render();
};
$("fillEmpty").onclick=async()=>{
    if(aligning||!await askConfirmation("未分類の交点をすべて「空」にします。その後、石のある交点を黒・白へ必ず修正し、盤全体を確認してください。"))return;
    remember();data.labels=data.labels.map(v=>v===null?"empty":v);changed();
};
$("applyReference").onclick=async()=>{
    if(aligning||!data.referenceDraft||data.labels.some(v=>v!==null))return;
    if(!await askConfirmation("参考写真と石の配置・行列の向きが同じであることを確認しましたか？ ラベルを下書きにします。写真全体と照合し、違いを修正してから分類を完了してください。"))return;
    remember();data.labels=[...data.referenceDraft.labels];data.referenceApplied=true;changed();
};
$("finish").onclick=async()=>{
    if(aligning||data.labels.includes(null))return;
    if(!await askConfirmation("盤全体の空・黒・白・判別不能のラベルを見直しましたか？"))return;
    remember();data.reviewCompleted=true;scheduleSave();render();
};
$("download").onclick=()=>{
    const blob=new Blob([JSON.stringify(data,null,2)+"\n"],{type:"application/json"}),url=URL.createObjectURL(blob);
    const link=document.createElement("a");link.href=url;link.download=data.datasetId+"-labels.json";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
$("import").onchange=async event=>{
    const file=event.target.files[0];if(!file)return;
    try {
        const imported=JSON.parse(await file.text());
        for(const key of ["schemaVersion","datasetId","captureGroup","sourceSha256","width","height","coordinateConvention"])
            if(imported[key]!==data[key])throw new Error("別の画像・データセットです");
        if(data.referenceDraft&&(JSON.stringify(imported.referenceDraft)!==JSON.stringify(data.referenceDraft)||typeof imported.referenceApplied!=="boolean"||imported.referenceApplied&&!imported.geometryReviewed))throw new Error("参考GTの出典・適用状態が違います");
        if(!Array.isArray(imported.labels)||imported.labels.length!==361||imported.labels.some(v=>v!==null&&(typeof v!=="string"||!Object.hasOwn(names,v))))throw new Error("ラベル形式が違います");
        if(typeof imported.geometryReviewed!=="boolean"||typeof imported.reviewCompleted!=="boolean")throw new Error("確認状態が不正です");
        const previous=data;
        data={...data,corners:imported.corners};
        const valid=validGeometry();data=previous;
        if(!valid||(!imported.geometryReviewed&&imported.labels.some(v=>v!==null))||(imported.reviewCompleted&&imported.labels.includes(null)))throw new Error("位置合わせ・完了状態が不正です");
        if(!await askConfirmation("現在のラベルをこのJSONで置き換えますか？"))return;
        remember();data={...data,corners:imported.corners,labels:imported.labels,geometryReviewed:imported.geometryReviewed,reviewCompleted:imported.reviewCompleted};
        if(data.referenceDraft)data.referenceApplied=imported.referenceApplied;
        aligning=!data.geometryReviewed;scheduleSave();render();
    } catch(error){status("読み込めません："+error.message,"error");}
    event.target.value="";
};
window.addEventListener("keydown",event=>{
    if(!data||$("confirmation").open||["INPUT","TEXTAREA","SELECT"].includes(document.activeElement.tagName)||event.ctrlKey||event.metaKey||event.altKey)return;
    const labels={"0":"empty","1":"black","2":"white","3":"unknown"};
    if(Object.hasOwn(labels,event.key)){event.preventDefault();assign(labels[event.key]);return;}
    const delta={ArrowLeft:-1,ArrowRight:1,ArrowUp:-19,ArrowDown:19}[event.key];
    if(delta!==undefined){event.preventDefault();selected=(selected+delta+361)%361;render();}
    if(event.key==="Delete"||event.key==="Backspace"){event.preventDefault();assign(null);}
});
window.addEventListener("resize",render);
(async()=>{
    try {
        const response=await fetch("/api/data");if(!response.ok)throw new Error("データを読み込めません");
        const result=await response.json();data=result.data;token=result.token;aligning=!data.geometryReviewed;
        photo.onload=()=>{canvas.width=data.width;canvas.height=data.height;render();};
        photo.onerror=()=>status("写真を読み込めませんでした", "error");photo.src="/source.png";
        status(data.savedAt?"PCに保存済み · "+new Date(data.savedAt).toLocaleTimeString("ja-JP"):"未分類で開始 · PC内に保存");
    } catch(error){status(error.message,"error");}
})();
