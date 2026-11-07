const {test}=require('node:test');
const assert=require('node:assert/strict');
const {saveLabelSnapshot}=require('./save-transport.js');
const snapshot={datasetId:'synthetic',sourceSha256:'source',labels:['black']};
const response=value=>({ok:true,status:200,json:async()=>value});
const ack={revision:1,savedAt:'synthetic-time'};

test('successful save sends one request without changing the snapshot',async()=>{
  const before=JSON.stringify(snapshot);let calls=0;
  const result=await saveLabelSnapshot(snapshot,0,'test-token',async(url,options)=>{
    calls++;assert.equal(url,'/api/save');
    const body=JSON.parse(options.body);assert.equal(body.expectedRevision,0);assert.ok(body.saveId);return response(ack);
  });
  assert.deepEqual(result,ack);assert.equal(calls,1);assert.equal(JSON.stringify(snapshot),before);
});

test('lost acknowledgement is recovered only from its own save receipt',async()=>{
  let id,calls=0;
  const result=await saveLabelSnapshot(snapshot,0,'test-token',async(url,options)=>{
    calls++;
    if(url==='/api/save'){id=JSON.parse(options.body).saveId;throw new TypeError('reply lost');}
    return response({data:{...snapshot,revision:1},lastSave:{saveId:id,expectedRevision:0,...ack}});
  });
  assert.deepEqual(result,ack);assert.equal(calls,2);
});

test('a failed request is retried with the same ID and same payload',async()=>{
  const bodies=[];
  const result=await saveLabelSnapshot(snapshot,0,'test-token',async(url,options)=>{
    if(url==='/api/data')return response({data:{...snapshot,revision:0},lastSave:null});
    bodies.push(options.body);if(bodies.length===1)throw new TypeError('not delivered');return response(ack);
  });
  assert.deepEqual(result,ack);assert.equal(bodies.length,2);assert.equal(bodies[0],bodies[1]);
});

test('another writer is never merged or overwritten',async()=>{
  let posts=0;
  await assert.rejects(saveLabelSnapshot(snapshot,0,'test-token',async url=>{
    if(url==='/api/save'){posts++;throw new TypeError('reply lost');}
    return response({data:{...snapshot,revision:1},lastSave:{saveId:'another-writer',expectedRevision:0,...ack}});
  }),/別の更新/);
  assert.equal(posts,1);
});

test('HTTP conflict is returned without retrying',async()=>{
  let calls=0;
  await assert.rejects(saveLabelSnapshot(snapshot,0,'test-token',async()=>{
    calls++;return {ok:false,status:409,json:async()=>({error:'conflict'})};
  }),/conflict/);assert.equal(calls,1);
});

test('unreachable server is bounded and never reported as saved',async()=>{
  let posts=0;
  await assert.rejects(saveLabelSnapshot(snapshot,0,'test-token',async url=>{
    if(url==='/api/save')posts++;throw new TypeError('unreachable');
  }),/入力をJSONへ退避/);assert.equal(posts,2);
});

test('an incomplete receipt or another dataset is not accepted',async()=>{
  for(const wrongDataset of [false,true]) {
    await assert.rejects(saveLabelSnapshot(snapshot,0,'test-token',async(url,options)=>{
      if(url==='/api/save')throw new TypeError('reply lost');
      return response({data:{...snapshot,datasetId:wrongDataset?'other':'synthetic',revision:1},
        lastSave:{saveId:'not-this-save',expectedRevision:0,...ack}});
    }),wrongDataset?/別のデータセット/:/別の更新/);
  }
});
