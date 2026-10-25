"""正解manifestと19行の予測盤面を比較する。モデルや正解の推測は行わない。"""
import argparse
import json
import re
from pathlib import Path

STATES = ("empty", "black", "white", "unknown")
SYMBOLS = {".": "empty", "B": "black", "W": "white", "?": "unknown"}


def read_predictions(text):
    rows = {}
    for line in text.splitlines():
        match = re.fullmatch(r"(\d{2}) ([.BW?]{19})", line)
        if match:
            row = int(match[1])
            if row not in range(1, 20) or row in rows:
                raise ValueError("予測の行番号が不正・重複しています")
            rows[row] = [SYMBOLS[symbol] for symbol in match[2]]
        elif re.match(r"^\d{2}\s", line):
            raise ValueError("予測は行番号と19交点分の . B W ? で指定します")
    if set(rows) != set(range(1, 20)):
        raise ValueError("予測には01〜19の全行が必要です")
    return [state for row in range(1, 20) for state in rows[row]]


def compare(manifest, predictions, method, classifier_ref):
    if len(predictions) != 361 or any(state not in STATES for state in predictions):
        raise ValueError("予測は361個の空・黒・白・不明です")
    samples = manifest.get("samples", [])
    positions = {}
    for sample in samples:
        row, column, truth = sample.get("row"), sample.get("column"), sample.get("label")
        if (type(row) is not int or type(column) is not int or row not in range(1, 20)
                or column not in range(1, 20) or truth not in STATES or (row, column) in positions):
            raise ValueError("正解の座標・ラベルが不正、または重複しています")
        positions[(row, column)] = truth
    if len(positions) != 361:
        raise ValueError("正解は361交点分必要です")
    matrix = {truth: {predicted: 0 for predicted in STATES} for truth in STATES}
    differences = []
    for index, prediction in enumerate(predictions):
        row, column = index // 19 + 1, index % 19 + 1
        truth = positions[(row, column)]
        matrix[truth][prediction] += 1
        if prediction != truth:
            differences.append(dict(row=row, column=column, truth=truth, prediction=prediction))
    per_class = {truth: dict(total=sum(matrix[truth].values()), correct=matrix[truth][truth],
                            unknown=matrix[truth]["unknown"],
                            wrong=sum(matrix[truth][state] for state in STATES if state not in (truth, "unknown")))
                 for truth in STATES[:3]}
    return dict(schemaVersion=1, datasetId=manifest["datasetId"], captureGroup=manifest["captureGroup"],
                sourceSha256=manifest["sourceSha256"], annotationRevision=manifest["annotationRevision"],
                method=method, classifierRef=classifier_ref, evaluationScope="one-image-development-check",
                split=manifest.get("split", "unassigned"), confusionMatrix=matrix, perClass=per_class,
                correctKnown=sum(item["correct"] for item in per_class.values()),
                wrongKnown=sum(item["wrong"] for item in per_class.values()),
                unknownKnown=sum(item["unknown"] for item in per_class.values()),
                excludedGroundTruthUnknown=sum(matrix["unknown"].values()), differences=differences)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--method", required=True)
    parser.add_argument("--classifier-ref", default="unspecified")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    predictions = read_predictions(args.predictions.read_text(encoding="utf-8-sig"))
    result = compare(manifest, predictions, args.method, args.classifier_ref)
    captures = (Path(__file__).resolve().parents[2] / "captures").resolve()
    if not args.output.resolve().is_relative_to(captures):
        raise ValueError("個人の正解・予測の出力先はcaptures配下にしてください")
    # 過去の比較結果を黙って上書きしない。
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps({key: result[key] for key in ("correctKnown", "wrongKnown", "unknownKnown", "perClass")}, ensure_ascii=False))
