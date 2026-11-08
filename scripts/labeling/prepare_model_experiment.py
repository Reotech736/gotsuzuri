"""開発用GTだけで配置単位の比較分割を固定する。学習・推論は実行しない。"""
import argparse
import json
import re
from pathlib import Path

from assign_candidates import REPO, sha, write_json
from compare import compare, read_predictions
from server import validate_edit

EXPERIMENT = 'grouped-image-pilot-v1'


def make_folds(rows):
    ids, development, reserved = set(), [], []
    roles_by_group, roles_by_image, groups_by_image = {}, {}, {}
    for row in rows:
        dataset, group, role = (row.get(k) for k in ('datasetId', 'captureGroup', 'role'))
        if (not isinstance(dataset, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', dataset)
                or not isinstance(group, str) or not group or dataset in ids
                or role not in ('development', 'reserved-final-check')):
            raise ValueError('台帳のID・撮影グループ・役割が不正または重複しています')
        image_hash = row.get('sourceSha256')
        if not isinstance(image_hash, str) or not re.fullmatch('[0-9a-f]{64}', image_hash):
            raise ValueError('元画像ハッシュが不正です')
        ids.add(dataset)
        roles_by_group.setdefault(group, set()).add(role)
        roles_by_image.setdefault(image_hash, set()).add(role)
        groups_by_image.setdefault(image_hash, set()).add(group)
        (development if role == 'development' else reserved).append(row)
    if any(len(roles) != 1 for roles in [*roles_by_group.values(), *roles_by_image.values()]):
        raise ValueError('留保用と開発用に同じ配置または元画像があります')
    if any(len(groups) != 1 for groups in groups_by_image.values()):
        raise ValueError('同じ元画像を別の撮影グループへ分けられません')
    groups = sorted({r['captureGroup'] for r in development})
    if len(groups) < 3:
        raise ValueError('配置単位の比較には開発用3グループ以上が必要です')
    folds = [dict(validationGroup=g,
                  trainDatasets=sorted(r['datasetId'] for r in development if r['captureGroup'] != g),
                  validationDatasets=sorted(r['datasetId'] for r in development if r['captureGroup'] == g))
             for g in groups]
    return development, reserved, folds


def within_captures(path):
    path = path.resolve()
    if not path.is_relative_to((REPO/'captures').resolve()):
        raise ValueError('入出力はcaptures配下です')
    return path


def prepare(inventory_path, baseline_path, output):
    inventory_path, baseline_path, output = map(within_captures, (inventory_path, baseline_path, output))
    inventory_hash = sha(inventory_path)
    inventory = json.loads(inventory_path.read_bytes())
    development, reserved, folds = make_folds(inventory['datasets'])
    if len(development) != 7 or len(folds) != 3:
        raise ValueError('この実験計画v1は開発用7枚・3配置です')
    records, protected = [], {str(inventory_path.relative_to(REPO)): inventory_hash}
    # 留保用のGT・画像・manifestは開かない。台帳の役割だけで除外する。
    for item in sorted(development, key=lambda r: r['datasetId']):
        annotation = within_captures(REPO/item['annotationFile'])
        manifest_path = annotation.parent/'manifest.json'
        dataset = item['datasetId']
        source = within_captures(REPO/'captures/labeling'/dataset)
        policy = source/'holdout-policy.json'
        if policy.exists():
            # 台帳の役割を誤って開発用へ変えても、画像側の留保指定で止める。
            if json.loads(policy.read_bytes()).get('role') == 'reserved-final-check':
                raise ValueError('留保指定の画像は開発用にできません')
        if sha(annotation) != item['annotationSha256'] or sha(manifest_path) != item['manifestSha256']:
            raise ValueError('台帳と固定GTのハッシュが違います')
        gt = json.loads(annotation.read_bytes()); validate_edit(gt, gt)
        if (not gt['reviewCompleted'] or not gt['geometryReviewed'] or gt['datasetId'] != dataset
                or gt['captureGroup'] != item['captureGroup'] or gt['revision'] != item['annotationRevision']
                or gt['sourceSha256'] != item['sourceSha256']):
            raise ValueError('固定GTの完了状態・出典が違います')
        if sha(source/'original.bin') != item['sourceSha256']:
            raise ValueError('元画像ハッシュが違います')
        manifest = json.loads(manifest_path.read_bytes())
        for key, value in [('datasetId', dataset), ('captureGroup', gt['captureGroup']),
                           ('sourceSha256', gt['sourceSha256']), ('annotationRevision', gt['revision']), ('corners',gt['corners'])]:
            if manifest[key] != value:
                raise ValueError('manifestと固定GTの出典が違います')
        predictions_path, report_path = baseline_path/(dataset+'.txt'), baseline_path/(dataset+'-report.json')
        predictions = read_predictions(predictions_path.read_text(encoding='utf-8-sig'))
        report = json.loads(report_path.read_bytes())
        for p in (annotation, manifest_path, source/'original.bin', source/'source.png'):
            if report['inputSha256'].get(str(p.relative_to(REPO))) != sha(p):
                raise ValueError('基準評価時から画像または固定GTが変わっています')
        checked = compare(manifest, predictions, 'preparation-check', EXPERIMENT)
        if ([s['label'] for s in sorted(manifest['samples'],key=lambda s:(s['row'],s['column']))] != gt['labels']
                or checked['confusionMatrix'] != report['confusionMatrix']
                or any(report[k] != checked[k] for k in ('datasetId','captureGroup','sourceSha256','annotationRevision'))):
            raise ValueError('基準予測・manifest・GTが一致しません')
        inputs = [annotation, manifest_path, source/'original.bin', source/'source.png', predictions_path, report_path]
        protected.update({str(p.relative_to(REPO)): sha(p) for p in inputs})
        records.append(dict(item, labelCounts={s:gt['labels'].count(s) for s in ('empty','black','white','unknown')},
                            baseline={k:checked[k] for k in ('correctKnown','wrongKnown','unknownKnown','perClass')}))
    if protected != {p:sha(REPO/p) for p in protected}:
        raise ValueError('準備中に入力が変わりました')
    result = dict(schemaVersion=1, experimentId=EXPERIMENT, stage='prepared-not-trained',
                  development=records, folds=folds,
                  excludedReserved=[{k:r[k] for k in ('datasetId','captureGroup','role')} for r in reserved],
                  inputSha256=protected, inputsUnchanged=True, reservedContentRead=False,
                  preparationCodeSha256=sha(Path(__file__)))
    output.mkdir(parents=True, exist_ok=False)
    write_json(output/'experiment-data.json', result)
    print(json.dumps(dict(experiment=EXPERIMENT,developmentImages=len(records),folds=len(folds),
                          excludedReservedImages=len(reserved),trainingRun=False)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.inventory, args.baseline, args.output)
