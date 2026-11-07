"""固定GTと現行Kotlin判定のPC比較。閾値調整・学習・Android更新は行わない。"""
import argparse
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw
from assign_candidates import REPO, compile_probe, run, sha, write_json
from compare import STATES, compare, read_predictions
from server import project, validate_edit


def review_figure(source, snapshot, predictions, output):
    """保存結果の診断図。表示用縮小画像は認識へ戻さない。"""
    with Image.open(source) as original:
        photo = original.convert('RGB')
    photo.thumbnail((900, 1200))
    canvas = Image.new('RGB', (photo.width+440, max(photo.height+65, 990)), '#f2f4f8')
    canvas.paste(photo, (0, 65))
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 10), snapshot['datasetId'], fill='black')
    draw.text((12, 30), 'Red: wrong | Orange: unknown | Green: correct stone', fill='black')
    for i, (truth, prediction) in enumerate(zip(snapshot['labels'], predictions)):
        if truth == 'unknown':
            continue
        color = '#e94242' if prediction not in (truth, 'unknown') else '#ed9900' if prediction == 'unknown' else '#18a05e'
        if truth == prediction == 'empty':
            continue
        x, y = project(snapshot['corners'], i % 19, i // 19)
        x, y = x*(photo.width-1), 65+y*(photo.height-1)
        draw.ellipse((x-6, y-6, x+6, y+6), outline=color, width=2)
    for title, labels, top in [('GT (user reviewed)', snapshot['labels'], 65), ('Prediction (fixed baseline)', predictions, 520)]:
        left, spacing = photo.width+32, 20
        draw.text((left, top), title+' / top-left = r1 c1', fill='black')
        top += 35
        draw.rectangle((left-12, top-12, left+372, top+372), fill='#d5b16f')
        for line in range(19):
            draw.line((left, top+line*spacing, left+360, top+line*spacing), fill='#59452c')
            draw.line((left+line*spacing, top, left+line*spacing, top+360), fill='#59452c')
        for i, state in enumerate(labels):
            x, y = left+(i % 19)*spacing, top+(i // 19)*spacing
            if state in ('black', 'white'):
                draw.ellipse((x-8,y-8,x+8,y+8), fill=state, outline='#333333')
            elif state == 'unknown':
                draw.text((x-3,y-6), '?', fill='#a53800')
    canvas.save(output)


def parse_baseline(raw):
    positions = {}
    for line in raw.splitlines():
        fields = line.split('\t')
        if len(fields) != 4 or fields[0] != 'B':
            raise ValueError('現行判定以外の出力です')
        column, row = int(fields[1]), int(fields[2])
        state = fields[3].lower()
        if (row not in range(19) or column not in range(19) or state not in STATES
                or (row, column) in positions):
            raise ValueError('現行判定の座標・状態が不正または重複しています')
        positions[(row, column)] = state
    if len(positions) != 361:
        raise ValueError('現行判定が361点そろっていません')
    return [positions[(r, c)] for r in range(19) for c in range(19)]


def evaluate(args):
    output = args.output.resolve()
    if not output.is_relative_to((REPO/'captures').resolve()):
        raise ValueError('出力先はcaptures配下です')
    output.mkdir(parents=True, exist_ok=False)
    cp, code_hashes = compile_probe(args.jdk, args.gradle_cache, output)
    code_hashes[Path(__file__).name] = sha(Path(__file__))
    results, protected = [], {}
    dataset_ids = set()
    for folder in args.source:
        if not folder.resolve().is_relative_to((REPO/'captures').resolve()):
            raise ValueError('入力はcaptures配下です')
        snapshot_path, manifest_path = folder/'annotations-reviewed.json', folder/'manifest.json'
        snapshot = json.loads(snapshot_path.read_bytes())
        manifest = json.loads(manifest_path.read_bytes())
        validate_edit(snapshot, snapshot)
        if not snapshot['reviewCompleted'] or not snapshot['geometryReviewed']:
            raise ValueError('未完了GTです')
        dataset = snapshot['datasetId']
        if not isinstance(dataset, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', dataset):
            raise ValueError('データセットIDが不正です')
        if dataset in dataset_ids:
            raise ValueError('同じデータセットを重複評価できません')
        dataset_ids.add(dataset)
        source = folder.parent/dataset
        inputs = [snapshot_path, manifest_path, source/'annotations.json', source/'original.bin', source/'source.png']
        for path in inputs:
            if not path.resolve().is_relative_to((REPO/'captures').resolve()):
                raise ValueError('入力はcaptures配下です')
        hashes = {str(p.resolve().relative_to(REPO)): sha(p) for p in inputs}
        protected.update(hashes)
        if sha(source/'original.bin') != snapshot['sourceSha256']:
            raise ValueError('元画像のハッシュが違います')
        for key, value in [('datasetId', dataset), ('captureGroup', snapshot['captureGroup']),
                           ('sourceSha256', snapshot['sourceSha256']), ('annotationRevision', snapshot['revision']),
                           ('corners', snapshot['corners'])]:
            if manifest[key] != value:
                raise ValueError('manifestと固定GTの出典が違います')
        # compareも全座標・重複・状態を検証する。
        compare(manifest, ['unknown']*361, 'validation', code_hashes)
        labels = [s['label'] for s in sorted(manifest['samples'], key=lambda s: (s['row'], s['column']))]
        if labels != snapshot['labels']:
            raise ValueError('manifestと固定GTのラベルが違います')
        # GTのラベル・石数はJavaへ渡さない。
        raw = run([args.jdk/'java.exe', '-cp', cp, 'CandidateProbe', source/'source.png',
                   *[v for point in snapshot['corners'] for v in point]])
        predictions = parse_baseline(raw)
        report = compare(manifest, predictions, 'recompiled-baseline-java2d-2048', code_hashes)
        prior_text, prior_report = folder/'baseline-2048.txt', folder/'baseline-2048-report.json'
        reproduced = None
        if prior_text.exists() or prior_report.exists():
            if (predictions != read_predictions(prior_text.read_text(encoding='utf-8-sig')) or
                    report['confusionMatrix'] != json.loads(prior_report.read_bytes())['confusionMatrix']):
                raise ValueError('既存の固定基準値を再現できません')
            reproduced = True
        report.update(inputSha256=hashes, priorBaselineReproduced=reproduced)
        write_json(output/(dataset+'-report.json'), report)
        with (output/(dataset+'-probe.tsv')).open('x', encoding='utf-8') as stream:
            stream.write(raw)
        symbols = dict(empty='.', black='B', white='W', unknown='?')
        with (output/(dataset+'.txt')).open('x', encoding='utf-8') as stream:
            stream.write('\n'.join(f'{r+1:02d} '+''.join(symbols[p] for p in predictions[r*19:(r+1)*19])
                                   for r in range(19))+'\n')
        review_figure(source/'source.png', snapshot, predictions, output/(dataset+'-review.png'))
        result = {k: report[k] for k in ('datasetId', 'captureGroup', 'annotationRevision', 'correctKnown',
                                        'wrongKnown', 'unknownKnown', 'perClass', 'confusionMatrix')}
        results.append(result)
        print(json.dumps(result), flush=True)
    if protected != {p: sha(REPO/p) for p in protected}:
        raise ValueError('評価中に入力が変わりました')
    write_json(output/'summary.json', dict(schemaVersion=1, codeSha256=code_hashes, results=results,
               captureGroups=sorted({r['captureGroup'] for r in results}), inputsUnchanged=True,
               scope='development-check-grouped-by-arrangement-not-independent-generalization-test'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jdk', type=Path, required=True)
    parser.add_argument('--gradle-cache', type=Path, default=Path.home()/'.gradle/caches/modules-2/files-2.1')
    evaluate(parser.parse_args())
