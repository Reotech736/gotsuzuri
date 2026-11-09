"""採用台帳の固定GTを写真と模式図で照合する。編集・推論はしない。"""
import argparse
import json
import re
import shutil
from collections import Counter
from pathlib import Path

from PIL import Image

from server import project, validate_edit
from visualize_assignments import HERE, REPO, sha, within_captures, serve


def build(inventory, output):
    inventory, output = map(within_captures, (inventory, output))
    data = json.loads(inventory.read_bytes())
    protected = {str(inventory.relative_to(REPO)): sha(inventory)}
    views, sources, ids = [], [], set()
    for row in data['datasets']:
        name = row['datasetId']
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', name) or name in ids or name in data.get('supersededDatasets', []):
            raise ValueError('重複または使用禁止のGTです')
        ids.add(name)
        annotation = within_captures(REPO / row['annotationFile'])
        manifest = annotation.parent / 'manifest.json'
        source = within_captures(REPO / 'captures/labeling' / name / 'source.png')
        original = source.parent / 'original.bin'
        if sha(annotation) != row['annotationSha256'] or sha(manifest) != row['manifestSha256']:
            raise ValueError('固定GTと台帳のハッシュが違います')
        gt = json.loads(annotation.read_bytes()); validate_edit(gt, gt)
        if (not gt['reviewCompleted'] or gt['datasetId'] != name or
                gt['revision'] != row['annotationRevision'] or gt['captureGroup'] != row['captureGroup'] or
                gt['sourceSha256'] != row['sourceSha256'] or sha(original) != gt['sourceSha256']):
            raise ValueError('固定GTの完了・出典が違います')
        samples = json.loads(manifest.read_bytes())['samples']
        if [s['label'] for s in samples] != gt['labels']:
            raise ValueError('manifestのラベルが違います')
        for path in (annotation, manifest, source, original):
            protected[str(path.relative_to(REPO))] = sha(path)
        views.append(dict(dataset=name, group=gt['captureGroup'], role=row['role'], revision=gt['revision'],
                          width=gt['width'], height=gt['height'], counts=dict(Counter(gt['labels'])),
                          preview=name+'.jpg', original=name+'.png',
                          sites=[dict(row=i//19+1, column=i%19+1, truth=label,
                                      image=project(gt['corners'], i%19, i//19))
                                 for i, label in enumerate(gt['labels'])]))
        sources.append((name, source))
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(HERE/'gt-review.html', output/'index.html')
    shutil.copyfile(HERE/'gt-review.js', output/'gt-review.js')
    for name, source in sources:
        shutil.copyfile(source, output/(name+'.png'))
        with Image.open(source) as im:
            im.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
            im.convert('RGB').save(output/(name+'.jpg'), quality=95)
    (output/'view-data.json').write_text(json.dumps(dict(views=views), ensure_ascii=False), encoding='utf-8')
    (output/'provenance.json').write_text(json.dumps(dict(inputSha256=protected), indent=2), encoding='utf-8')
    if any(sha(REPO/path) != digest for path, digest in protected.items()):
        raise ValueError('準備中に入力が変わりました')
    return views


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    if args.inventory:
        print(f'{len(build(args.inventory, args.output))}枚の固定GTを準備しました。', flush=True)
    if args.serve:
        serve(args.output)
