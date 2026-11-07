# 配置BのGT完了と現行PC判定の比較

2026-11-08、本人が固定位置写真の分類完了を報告した後、PCに保存されたGTを確認・固定し、配置Bの上方／固定位置を現行方式で比較した。方式・閾値・GTは変更していない。Android本体・端末・モデル学習・AWS利用には進んでいない。

## GTの保存確認

- 上方：`arrangement-b-top-20261107` 更新232。
- 固定位置：`arrangement-b-fixed-ref-20261107` 更新7。
- 両方とも位置合わせ・分類完了、空234・黒63・白64・判別不能0・未分類0で、全361点一致。
- 固定位置は本人が参考GTを適用した記録があり、referenceApplied=true。参考の出典が上方の固定GT更新232・JSONハッシュと一致することを確認した。

固定位置も新しい`arrangement-b-fixed-ref-20261107-crops/`へ原寸361切り出し・manifest・annotations-reviewed.jsonを保存した。元JPEGハッシュ、manifestの全ラベル、書き出し前後の元GT非変更を確認した。元写真・GT・派生画像はcaptures内だけで保管する。

## 比較結果

| 配置Bの写真 | 正解 | 誤った確定判定 | 不明 |
| --- | ---: | ---: | ---: |
| 上方 | 317 | 20 | 24 |
| 固定位置 | 291 | 7 | 63 |

| 写真・GT | 正解 | 誤り | 不明 |
| --- | ---: | ---: | ---: |
| 上方・空234 | 199 | 20 | 15 |
| 上方・黒63 | 54 | 0 | 9 |
| 上方・白64 | 64 | 0 | 0 |
| 固定位置・空234 | 203 | 7 | 24 |
| 固定位置・黒63 | 43 | 0 | 20 |
| 固定位置・白64 | 45 | 0 | 19 |

上方の誤り20点は全て空→白。11行19列から右側・下側の16〜19列へ集中し、図でも明るい木地に重なる。配置A上方と同じく、明るい木地を白石とする問題が別配置でも出た。反射・露出・色基準等のどれが主要因かは未確定で、照明だけを変えた対照実験はまだない。

固定位置の誤り7点も全て空→石（黒3・白4）。奥側の1行8〜12列では、2行目の並びに対応する白黒白黒白を1行目に誤検出している。ほかは2行16列の白、7行8列の黒。物体の対応そのものを追跡したわけではないが、斜め撮影の見かけの位置と本来の交点の混同を疑う具体例になる。単純な一定移動量の補正は以前のPC試作で盤全体が悪化したため、この結果だけで再採用しない。

石127点だけを見ると、上方は正解118・不明9、固定位置は正解88・不明39。今回、本物の石を別色や空へ確定した誤りはないが、不明の石を見逃しとして扱う必要は残る。不明を空へ一括置換しない。密集と角度の影響は混在しており、配置Aと石数・配置・撮影条件が異なるので、合計値の差を隣接だけの影響とは断定しない。

## 再現性と成果物

`scripts/labeling/evaluate_baseline.py`で現在のKotlinをPC専用に再コンパイルし、既存5枚と配置B2枚の計7枚を実行した。GTのラベル・石数は推論へ渡さず、画像と本人指定の四隅だけを使った。Java2Dの長辺2048・bilinear縮小で、Androidの実機結果とは区別する。

```powershell
python scripts/labeling/evaluate_baseline.py --source captures/labeling/reference-top-20261025-crops --source captures/labeling/oblique-low-20261025-crops --source captures/labeling/oblique-high-20261025-crops --source captures/labeling/arrangement-a-top-20261107-crops --source captures/labeling/arrangement-a-fixed-ref-20261107-crops --source captures/labeling/arrangement-b-top-20261107-crops --source captures/labeling/arrangement-b-fixed-ref-20261107-crops --output captures/labeling/baseline-three-groups-新しいID --jdk '.tools/jdk21/jdk-21.0.12.1+1/bin'
```

最終出力は`captures/labeling/baseline-three-groups-20261108-v1/`。写真別・クラス別のsummary、混同行列・全差分を含むreport、予測361点のtxt／probe.tsv、元写真＋GT図＋予測図のreview.pngを保存した。既存5枚は前回出力の予測全点と混同行列を完全再現。全7枚の主要入力ハッシュが実行前後で一致し、Bの診断図2枚を目視確認した。コードは変更しておらず、自動テストやAndroidビルドは再実行していない。

## 次の収集と限界

現在は7枚・3撮影グループで、全て開発用として分析済み。2,527交点を独立した撮影例と数えず、GTの十分な量や汎化精度とは扱わない。学習は未実施、未使用の最終確認用データもまだない。

次は合意済みの配置Cを上方／固定位置の2枚で記録し、GTを本人確認して留保する段階。A・Bと異なる配置で奥・中央・手前・盤端に石を置き、四隅を空け、2枚の間で石・照明・盤の向きを変えない。Cは方式・閾値・モデル選択が固まるまで予測比較・失敗例分析へ使わない。具体的な撮影・分離の手順は [GT収集計画](gt-collection-plan.md)。Cまで揃っても多様性や独立評価の十分さは保証しない。
