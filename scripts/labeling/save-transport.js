"use strict";
// 応答を失っても、自分の保存IDを確認できた場合だけ更新番号を進める。
(function () {
    async function saveLabelSnapshot(snapshot, expectedRevision, token, fetcher=fetch) {
        const saveId=crypto.randomUUID();
        const body=JSON.stringify({saveId,expectedRevision,data:snapshot});
        let lastError;
        for(let attempt=0;attempt<2;attempt++) {
            try {
                const response=await fetcher('/api/save',{method:'POST',headers:{'Content-Type':'application/json','X-Label-Token':token},
                    body,signal:AbortSignal.timeout(10000)});
                if(!response.ok) {
                    let result;
                    try { result=await response.json(); } catch (_) { result={}; }
                    const error=new Error(result.error||`保存できませんでした（HTTP ${response.status}）`);
                    error.httpFailure=true;
                    throw error;
                }
                const result=await response.json();
                if(!Number.isInteger(result.revision)||result.revision!==expectedRevision+1||typeof result.savedAt!=='string')throw new Error('保存の応答が不完全です');
                return result;
            } catch(error) {
                if(error.httpFailure)throw error;
                lastError=error;
                let live;
                try {
                    const response=await fetcher('/api/data',{signal:AbortSignal.timeout(5000)});
                    if(response.ok)live=await response.json();
                } catch (_) { /* 再送は同じ保存ID・同じ入力。返答を確認できなければ完了にしない。 */ }
                if(live) {
                    if(live.data.datasetId!==snapshot.datasetId||live.data.sourceSha256!==snapshot.sourceSha256)throw new Error('別のデータセットです。JSONを退避してください');
                    const receipt=live.lastSave;
                    if(receipt?.saveId===saveId && receipt.expectedRevision===expectedRevision &&
                       receipt.revision===expectedRevision+1 && live.data.revision===receipt.revision && typeof receipt.savedAt==='string') {
                        return {revision:receipt.revision,savedAt:receipt.savedAt};
                    }
                    if(live.data.revision!==expectedRevision)throw new Error('別の更新があるため保存を止めました。JSONを退避してください');
                }
            }
        }
        throw new Error(`通信を確認できず保存を止めました。入力をJSONへ退避してください（${lastError?.message||'通信失敗'}）`);
    }
    if(typeof module!=='undefined')module.exports={saveLabelSnapshot};
    else window.saveLabelSnapshot=saveLabelSnapshot;
})();
