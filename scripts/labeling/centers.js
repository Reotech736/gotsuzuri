"use strict";
const $=id=>document.getElementById(id);
const target=$("target"),reference=$("reference");
let data,token,index=0,dirty=false,saving=false,failed=false,timer,image=null,refImage=null,loadVersion=0;
function status(text,error=false){$("saveStatus").textContent=text;$("saveStatus").className=error?"error":"";}
function schedule(){data.reviewCompleted=false;dirty=true;status("未保存の変更があります…");clearTimeout(timer);timer=setTimeout(save,180);render();}
async function save(){
    if(saving||failed||!dirty)return;saving=true;
    try{
        while(dirty){
            dirty=false;const snapshot=structuredClone(data);
            const response=await fetch("/api/save",{method:"POST",headers:{"Content-Type":"application/json","X-Label-Token":token},body:JSON.stringify({expectedRevision:data.revision,data:snapshot})});
            const result=await response.json();if(!response.ok)throw new Error(result.error||"保存できませんでした");
            data.revision=result.revision;data.savedAt=result.savedAt;
        }
        status("PCに保存済み · "+new Date(data.savedAt).toLocaleTimeString("ja-JP"));$("retrySave").hidden=true;
    }catch(error){dirty=true;failed=true;status("保存失敗："+error.message,true);$("retrySave").hidden=false;}finally{saving=false;}
}
$("retrySave").onclick=()=>{failed=false;save();};
window.addEventListener("beforeunload",event=>{if(dirty||saving){event.preventDefault();event.returnValue="";}});
function cross(context,p,color,scale){
    const [x,y]=p;
    for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]){
        context.beginPath();context.moveTo(x+dx*3*scale,y+dy*3*scale);context.lineTo(x+dx*12*scale,y+dy*12*scale);
        context.strokeStyle="#111";context.lineWidth=3*scale;context.stroke();context.strokeStyle=color;context.lineWidth=1.5*scale;context.stroke();
    }
}
function draw(canvas,photo,logical,center){
    const context=canvas.getContext("2d");context.clearRect(0,0,canvas.width,canvas.height);
    if(!photo)return;context.drawImage(photo,0,0);
    const scale=canvas.width/Math.max(1,canvas.getBoundingClientRect().width);
    cross(context,logical,"#30d4e2",scale);if(center)cross(context,center,"#ff4aa0",scale);
}
function render(){
    if(!data)return;const task=data.tasks[index],entry=data.centers[index];
    $("taskTitle").textContent=`${index+1} / ${data.tasks.length} · ${task.row}行・${task.column}列の${task.label==="black"?"黒石":"白石"}`;
    $("taskSource").textContent=task.datasetId;
    $("selectedStatus").textContent=entry.status==="marked"?"中心を指定済み。写真を確認して次へ進めます。":entry.status==="unobservable"?"中心を判断できない、と記録しています。":"まだ中心を指定していません。";
    const count=data.centers.filter(e=>e.status!=="pending").length;
    $("progress").textContent=`確認済み ${count} / ${data.tasks.length}`;
    $("finish").textContent=`${data.tasks.length}か所の確認を完了`;
    $("finish").disabled=count!==data.tasks.length||data.reviewCompleted;
    $("completion").textContent=data.reviewCompleted?"全対象の確認完了として記録しています。":"";
    $("previous").disabled=index===0;$("next").disabled=index===data.tasks.length-1;
    draw(target,image,task.intersectionInCrop,entry.centerInCrop);draw(reference,refImage,task.referenceIntersection,null);
}
async function showTask(){
    const version=++loadVersion;image=refImage=null;target.style.pointerEvents="none";
    const task=data.tasks[index];target.width=task.width;target.height=task.height;render();
    try{
        const load=url=>new Promise((resolve,reject)=>{const p=new Image();p.onload=()=>resolve(p);p.onerror=()=>reject(new Error("写真を読み込めません"));p.src=url;});
        const [a,b]=await Promise.all([load('/'+task.file),load('/'+task.referenceFile)]);
        if(version!==loadVersion)return;image=a;refImage=b;reference.width=b.naturalWidth;reference.height=b.naturalHeight;target.style.pointerEvents="auto";render();
    }catch(error){status(error.message,true);}
}
target.onclick=event=>{
    if(!image)return;const rect=target.getBoundingClientRect(),task=data.tasks[index];
    const p=[(event.clientX-rect.left)/rect.width*task.width,(event.clientY-rect.top)/rect.height*task.height];
    if(p[0]<0||p[1]<0||p[0]>=task.width||p[1]>=task.height)return;
    data.centers[index]={status:"marked",centerInCrop:p};schedule();
};
$("previous").onclick=()=>{if(index>0){index--;showTask();}};
$("next").onclick=()=>{if(index<data.tasks.length-1){index++;showTask();}};
$("clear").onclick=()=>{data.centers[index]={status:"pending",centerInCrop:null};schedule();};
$("unobservable").onclick=()=>{data.centers[index]={status:"unobservable",centerInCrop:null};schedule();};
$("finish").onclick=()=>{if(data.centers.some(e=>e.status==="pending"))return;data.reviewCompleted=true;dirty=true;save();render();};
$("download").onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:"application/json"}));const link=document.createElement("a");link.href=url;link.download=data.datasetId+".json";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
window.addEventListener("resize",render);
(async()=>{try{const response=await fetch("/api/data");if(!response.ok)throw new Error("データを読み込めません");const result=await response.json();data=result.data;token=result.token;status(data.savedAt?"PCに保存済み · "+new Date(data.savedAt).toLocaleTimeString("ja-JP"):"未確認で開始 · PC内に保存");await showTask();}catch(error){status(error.message,true);}})();
