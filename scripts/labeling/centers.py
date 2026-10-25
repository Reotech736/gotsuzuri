"""確認済みGTを保護し、少数の石の見かけ中心を別データとして記録する。"""
import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path

from PIL import Image

from server import HERE, atomic_json, validate_edit


def reviewed_export(folder):
    raw = (folder / "annotations-reviewed.json").read_bytes()
    data = json.loads(raw)
    validate_edit(data, data)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if not data["reviewCompleted"] or any(manifest[key] != data[key] for key in
            ("datasetId", "captureGroup", "sourceSha256", "corners")) or manifest["annotationRevision"] != data["revision"]:
        raise ValueError("本人確認済みGTと対応する書き出しを指定してください")
    return data, manifest, hashlib.sha256(raw).hexdigest()


def prepare_centers(sources, reference, output, dataset_id):
    captures = (HERE.parents[1] / "captures").resolve()
    if not output.resolve().is_relative_to(captures):
        raise ValueError("出力はcaptures配下に限定します")
    ref_data, ref_manifest, ref_hash = reviewed_export(reference)
    plans = []
    # 低角度の誤検出の直下にある4石。同じ石を2条件で確認する診断用選択。
    for folder in sources:
        data, manifest, snapshot_hash = reviewed_export(folder)
        if data["captureGroup"] != ref_data["captureGroup"]:
            raise ValueError("同じ配置の撮影グループを指定してください")
        for column in (3, 4, 5, 6):
            row = 2
            sample = next(s for s in manifest["samples"] if (s["row"], s["column"]) == (row, column))
            ref_sample = next(s for s in ref_manifest["samples"] if (s["row"], s["column"]) == (row, column))
            index = (row - 1) * 19 + column - 1
            if sample["label"] not in ("black", "white") or sample["label"] != data["labels"][index] or sample["label"] != ref_sample["label"] or sample["label"] != ref_data["labels"][index]:
                raise ValueError("対象の石配置が一致しません")
            files = []
            for parent, entry in ((folder, sample), (reference, ref_sample)):
                file = (parent / entry["file"]).resolve()
                if file.parent != parent.resolve():
                    raise ValueError("切り出し画像の参照先が不正です")
                with Image.open(file) as image:
                    if list(image.size) != [entry["sourceBounds"][2]-entry["sourceBounds"][0], entry["sourceBounds"][3]-entry["sourceBounds"][1]]:
                        raise ValueError("切り出し範囲と画像寸法が一致しません")
                    files.append((file, list(image.size), hashlib.sha256(file.read_bytes()).hexdigest()))
            plans.append((data, sample, ref_sample, snapshot_hash, files))
    output.mkdir(parents=True, exist_ok=False)
    tasks = []
    for number, (data, sample, ref_sample, snapshot_hash, files) in enumerate(plans, 1):
        filename, ref_filename = f"crop-{number:02d}.png", f"reference-{number:02d}.png"
        shutil.copyfile(files[0][0], output / filename)
        shutil.copyfile(files[1][0], output / ref_filename)
        tasks.append(dict(id=number, datasetId=data["datasetId"], captureGroup=data["captureGroup"],
            sourceSha256=data["sourceSha256"], annotationRevision=data["revision"], annotationSha256=snapshot_hash,
            row=sample["row"], column=sample["column"], label=sample["label"],
            file=filename, width=files[0][1][0], height=files[0][1][1], cropSha256=files[0][2],
            sourceBounds=sample["sourceBounds"], sourceWidth=data["width"], sourceHeight=data["height"],
            intersectionInCrop=sample["intersectionInCrop"], referenceFile=ref_filename,
            referenceIntersection=ref_sample["intersectionInCrop"], referenceSha256=files[1][2],
            referenceDatasetId=ref_data["datasetId"], referenceAnnotationSha256=ref_hash))
    data = dict(schemaVersion=1, kind="stone-center-study", datasetId=dataset_id,
                sourceSha256=hashlib.sha256(json.dumps(tasks, sort_keys=True).encode()).hexdigest(), tasks=tasks,
                centers=[dict(status="pending", centerInCrop=None) for _ in tasks],
                coordinateConvention="native-crop-pixels-x-right-y-down", reviewCompleted=False, revision=0, savedAt=None)
    atomic_json(output / "annotations.json", data)
    return data


def validate_centers(current, candidate):
    if not isinstance(candidate, dict) or any(candidate.get(key) != current[key] for key in
            ("schemaVersion", "kind", "datasetId", "sourceSha256", "tasks", "coordinateConvention")):
        raise ValueError("別の画像・GTの中心データは保存できません")
    centers = candidate.get("centers")
    if not isinstance(centers, list) or len(centers) != len(current["tasks"]):
        raise ValueError("中心データの件数が違います")
    for task, entry in zip(current["tasks"], centers):
        if not isinstance(entry, dict) or set(entry) != {"status", "centerInCrop"}:
            raise ValueError("中心データの形式が違います")
        state, point = entry["status"], entry["centerInCrop"]
        if state not in ("pending", "marked", "unobservable"):
            raise ValueError("確認状態が不正です")
        if state == "marked":
            if not isinstance(point, list) or len(point) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in point) or not (0 <= point[0] < task["width"] and 0 <= point[1] < task["height"]):
                raise ValueError("中心は切り出し画像内を指定してください")
        elif point is not None:
            raise ValueError("未指定・見えない石に中心を推測で付けません")
    completed = candidate.get("reviewCompleted")
    if type(completed) is not bool or (completed and any(e["status"] == "pending" for e in centers)):
        raise ValueError("未確認の石が残っています")
    return dict(current, centers=centers, reviewCompleted=completed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, action="append", required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--id", required=True)
    args = parser.parse_args()
    prepare_centers(args.source, args.reference, args.output, args.id)
    print("未確認の石中心データを作成しました。盤面GTは変更していません。")
