// 人工データだけを127.0.0.1へ送る。GT・設定・外部ネットワークは使わない。
'use strict';
const http=require('node:http');
const net=require('node:net');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const args=process.argv.slice(2);
function option(name,fallback){const i=args.indexOf(name);return i<0?fallback:args[i+1];}
const attempts=Number(option('--attempts','12'));
const sizes=option('--sizes','1024,65536,1048576').split(',').map(Number);
const timeout=1500;
if(!Number.isInteger(attempts)||attempts<1||attempts>50||sizes.some(s=>!Number.isInteger(s)||s<1||s>1048576))throw Error('invalid attempts/sizes');
const captures=path.resolve(__dirname,'../../captures');
const output=path.resolve(option('--output',path.join(captures,'diagnostics','localhost-'+new Date().toISOString().replace(/[:.]/g,'-')+'.json')));
if(!output.startsWith(captures+path.sep))throw Error('output must be under captures');
fs.mkdirSync(path.dirname(output),{recursive:true});
// 同じ出力を上書きしない。失敗しても作成済みの空ファイルを保持する。
const descriptor=fs.openSync(output,'wx');

async function check(mode,size){
  const payload=Buffer.alloc(size,120),digest=crypto.createHash('sha256').update(payload).digest('hex');
  let sent=0,serverErrors=0;
  const server=mode==='tcp'?net.createServer(socket=>{
    socket.setTimeout(timeout,()=>socket.destroy());
    socket.once('data',()=>socket.end(payload,()=>sent++));
    socket.on('error',()=>serverErrors++);
  }):http.createServer((req,res)=>{
    res.writeHead(200,{'Content-Length':size,'Connection':mode==='http-close'?'close':'keep-alive'});
    res.end(payload,()=>sent++);
  });
  if(mode!=='tcp'){
    server.on('clientError',(_,socket)=>{serverErrors++;socket.destroy();});
    server.requestTimeout=timeout;server.keepAliveTimeout=timeout;
  }
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  const port=server.address().port,agent=mode==='http-keepalive'?new http.Agent({keepAlive:true,maxSockets:1}):false;
  const runs=[];
  try{
    for(let i=0;i<attempts;i++){
      runs.push(await new Promise(resolve=>{
        let received=0,finished=false;const hash=crypto.createHash('sha256');
        const requestAgent=mode==='http-keepalive-fresh'?new http.Agent({keepAlive:true,maxSockets:1}):agent;
        const start=performance.now();let connection;
        const finish=error=>{
          if(finished)return;finished=true;clearTimeout(deadline);
          if(mode==='http-keepalive-fresh')requestAgent.destroy();
          const contentValid=!error&&received===size&&hash.digest('hex')===digest;
          resolve({ok:contentValid,received,error:error||(!contentValid?'content-mismatch':null),elapsedMs:Math.round(performance.now()-start)});
        };
        const deadline=setTimeout(()=>{finish('deadline');connection?.destroy();},timeout);
        const data=chunk=>{received+=chunk.length;hash.update(chunk);};
        if(mode==='tcp'){
          connection=net.createConnection({host:'127.0.0.1',port},()=>connection.write('q'));
          connection.on('data',chunk=>{data(chunk);if(received>=size){finish(null);connection.destroy();}});
          connection.on('end',()=>finish(null));connection.on('error',e=>finish(e.code||e.message));
        }else{
          connection=http.get({host:'127.0.0.1',port,path:'/',agent:requestAgent},res=>{
            res.on('data',data);res.on('end',()=>finish(null));res.on('error',e=>finish(e.code||e.message));
          });
          connection.on('error',e=>finish(e.code||e.message));
        }
      }));
    }
  }finally{
    if(agent)agent.destroy();
    if(mode!=='tcp')server.closeAllConnections();
    await new Promise(resolve=>server.close(resolve));
  }
  return {mode,bytes:size,success:runs.filter(r=>r.ok).length,total:runs.length,serverSent:sent,serverErrors,
    failures:runs.filter(r=>!r.ok)};
}

(async()=>{
  try{
    const results=[];
    for(const mode of ['tcp','http-close','http-keepalive-fresh','http-keepalive'])for(const size of sizes){
      const result=await check(mode,size);results.push(result);console.log(JSON.stringify(result));
    }
    fs.writeFileSync(descriptor,JSON.stringify({schemaVersion:1,createdAt:new Date().toISOString(),node:process.version,
      platform:process.platform,timeoutMs:timeout,scope:'synthetic-loopback-only',results},null,2)+'\n');
    console.log('Report: '+output);
  }finally{fs.closeSync(descriptor);}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
