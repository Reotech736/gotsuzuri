"""石候補を集約して交点へ保守的に一対一対応させるPC試作。GTは評価専用。"""
import argparse
import hashlib
import json
import math
import os
import statistics
import subprocess
from pathlib import Path

from centers import validate_centers
from compare import compare, read_predictions
from server import project, validate_edit

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PARAMETERS = dict(step=.2, suppressionRadius=.65, assignmentRadius=.55,
                  ambiguityMargin=.15, emptyClearance=.8)


def inverse(corners, x, y):
    """射影の逆変換。座標は画像端基準、返値は交点間隔単位。"""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = corners
    dx1, dx2, dx3 = x1-x2, x3-x2, x0-x1+x2-x3
    dy1, dy2, dy3 = y1-y2, y3-y2, y0-y1+y2-y3
    det = dx1*dy2-dx2*dy1
    if abs(det) < 1e-12:
        raise ValueError("退化した射影です")
    g, h = (dx3*dy2-dx2*dy3)/det, (dx1*dy3-dx3*dy1)/det
    a, b, c, f = x1-x0+g*x1, x3-x0+h*x3, y1-y0+g*y1, y3-y0+h*y3
    aa, bb, cc, dd = a-x*g, b-x*h, c-y*g, f-y*h
    det = aa*dd-bb*cc
    if abs(det) < 1e-12:
        raise ValueError("逆射影できません")
    return [18*((x-x0)*dd-bb*(y-y0))/det, 18*(aa*(y-y0)-(x-x0)*cc)/det]


def aggregate(samples):
    """色支持率順の固定半径NMS。抑制点も保存し、連鎖による隣石の結合を避ける。"""
    if any(not all(math.isfinite(s[k]) for k in ('x', 'y', 'support'))
           or not (0 <= s['x'] <= 18 and 0 <= s['y'] <= 18 and 0 <= s['support'] <= 1) for s in samples):
        raise ValueError('画像サンプルの座標・支持率が不正です')
    remaining = sorted((s for s in samples if s['state'] in ('black', 'white')),
                       key=lambda s: (-s['support'], s['y'], s['x']))
    candidates = []
    while remaining:
        peak = remaining[0]
        members = [s for s in remaining if math.dist((s['x'], s['y']), (peak['x'], peak['y'])) < PARAMETERS['suppressionRadius']]
        remaining = [s for s in remaining if s not in members]
        # 異色が同じ物体範囲にある場合、どちらかを勝者として確定しない。
        candidates.append(dict(id=len(candidates), x=peak['x'], y=peak['y'], state=peak['state'],
                               support=peak['support'], mixed=len({s['state'] for s in members}) > 1,
                               members=members))
    return candidates


def assign(candidates, shift, empty_states):
    """全候補で競合を確認。曖昧な辺は未割当とし、第二候補へ押し込まない。"""
    if len(shift) != 2 or not all(math.isfinite(v) for v in shift):
        raise ValueError("位置ずれは有限な2座標です")
    if len(empty_states) != 361 or len({c['id'] for c in candidates}) != len(candidates):
        raise ValueError('361交点と重複しない候補IDが必要です')
    sites = [(c, r) for r in range(19) for c in range(19)]
    proposed, blocked, trace = {}, set(), []
    for candidate in candidates:
        p = (candidate['x']-shift[0], candidate['y']-shift[1])
        if not all(math.isfinite(v) for v in p):
            raise ValueError("候補座標が不正です")
        distances = sorted((math.dist(p, site), i) for i, site in enumerate(sites))
        distance, index = distances[0]
        entry = dict(candidateId=candidate['id'], correctedBoardCenter=p, distance=distance,
                     alternatives=[dict(index=i, distance=d) for d, i in distances[:2]], assignedIndex=None)
        if candidate.get('mixed'):
            entry['reason'] = 'mixed-colors'
        elif distance > PARAMETERS['assignmentRadius']:
            entry['reason'] = 'outside-gate'
        elif distances[1][0]-distance < PARAMETERS['ambiguityMargin']:
            entry['reason'] = 'ambiguous-sites'
        else:
            entry['reason'] = 'proposed'
            proposed.setdefault(index, []).append(entry)
        # 未割当の石を近くの空判定で消さない。
        blocked.update(i for d, i in distances if d < PARAMETERS['emptyClearance'])
        trace.append(entry)
    predictions = ['empty' if empty_states[i] == 'empty' and i not in blocked else 'unknown' for i in range(361)]
    for index, entries in proposed.items():
        if len(entries) == 1:
            entry = entries[0]
            # 他の曖昧候補が同じ交点を主張していたら確定しない。
            rivals = [e for e in trace if e is not entry and e['distance'] <= PARAMETERS['assignmentRadius']
                      and any(a['index'] == index and a['distance'] <= PARAMETERS['assignmentRadius'] for a in e['alternatives'])]
            if not rivals:
                entry.update(reason='assigned', assignedIndex=index)
                predictions[index] = next(c['state'] for c in candidates if c['id'] == entry['candidateId'])
                continue
        for entry in entries:
            entry['reason'] = 'candidate-collision'
    return predictions, trace


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def calibration(study_path, snapshot, snapshot_path):
    study = json.loads(study_path.read_bytes())
    validate_centers(study, study)
    if not study['reviewCompleted']:
        raise ValueError('中心確認が未完了です')
    offsets, used = [], []
    for task, center in zip(study['tasks'], study['centers']):
        if task['datasetId'] != snapshot['datasetId']:
            continue
        if (task['annotationSha256'] != sha(snapshot_path) or task['sourceSha256'] != snapshot['sourceSha256']
                or task['annotationRevision'] != snapshot['revision'] or task['captureGroup'] != snapshot['captureGroup']):
            raise ValueError('中心と固定GTの出典が違います')
        for key, hash_key in [('file', 'cropSha256'), ('referenceFile', 'referenceSha256')]:
            if sha(study_path.parent/task[key]) != task[hash_key]:
                raise ValueError('中心の画像ハッシュが違います')
        if center['status'] != 'marked':
            continue
        p = [(task['sourceBounds'][0]+center['centerInCrop'][0])/task['sourceWidth'],
             (task['sourceBounds'][1]+center['centerInCrop'][1])/task['sourceHeight']]
        board = inverse(snapshot['corners'], *p)
        offsets.append([board[0]-(task['column']-1), board[1]-(task['row']-1)])
        used.append(task['id'])  # 色ラベルは読み込まない。
    if not offsets:
        return [0., 0.], dict(kind='zero-no-manual-centers', taskIds=[])
    return [statistics.median(v[i] for v in offsets) for i in range(2)], dict(
        kind='manual-per-image-constant-translation', taskIds=used, studySha256=sha(study_path),
        revision=study['revision'], offsets=offsets)


def run(command):
    result = subprocess.run([str(v) for v in command], capture_output=True, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout


def compile_probe(jdk, cache, output):
    def jar(group, artifact, version):
        matches = sorted((cache/group/artifact/version).rglob(f'{artifact}-{version}.jar'))
        if len(matches) != 1:
            raise ValueError(f'キャッシュ内のJARを特定できません: {artifact} {version}')
        return matches[0]
    stdlib = jar('org.jetbrains.kotlin', 'kotlin-stdlib', '2.3.10')
    dependencies = [jar('org.jetbrains.kotlin', name, version) for name, version in (
        ('kotlin-compiler-embeddable', '2.3.10'), ('kotlin-stdlib', '2.3.10'),
        ('kotlin-script-runtime', '2.3.10'), ('kotlin-reflect', '1.6.10'),
        ('kotlin-daemon-embeddable', '2.3.10'))]
    dependencies += [jar('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm', '1.8.0'),
                     jar('org.jetbrains', 'annotations', '13.0')]
    classes = output/'classes'
    classes.mkdir()
    source = REPO/'app/src/main/java/io/github/reotech736/gotsuzuri'
    sources = [source/'BoardGeometry.kt', source/'StoneClassifier.kt']
    run([jdk/'java.exe', '-cp', os.pathsep.join(map(str, dependencies)),
         'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler', '-no-stdlib', '-no-reflect',
         '-classpath', os.pathsep.join(map(str, [stdlib, dependencies[-1]])), '-d', classes, *sources])
    cp = os.pathsep.join(map(str, [classes, stdlib]))
    run([jdk/'javac.exe', '-encoding', 'UTF-8', '-cp', cp, '-d', classes, HERE/'CandidateProbe.java'])
    return cp, {p.name: sha(p) for p in [*sources, HERE/'CandidateProbe.java', HERE/'assign_candidates.py', HERE/'compare.py']}


def evaluate(args):
    output = args.output.resolve()
    if not output.is_relative_to((REPO/'captures').resolve()):
        raise ValueError('出力先はcaptures配下です')
    output.mkdir(parents=True, exist_ok=False)
    cp, code_hashes = compile_probe(args.jdk, args.gradle_cache, output)
    summary = []
    for folder in args.source:
        snapshot_path = folder/'annotations-reviewed.json'
        snapshot = json.loads(snapshot_path.read_bytes())
        manifest_path = folder/'manifest.json'
        manifest = json.loads(manifest_path.read_bytes())
        validate_edit(snapshot, snapshot)
        if not snapshot['reviewCompleted']:
            raise ValueError('未完了GTです')
        source = folder.parent/snapshot['datasetId']
        protected = [snapshot_path, manifest_path, source/'annotations.json', source/'original.bin',
                     source/'source.png', args.centers]
        input_hashes = {str(p.resolve().relative_to(REPO)): sha(p) for p in protected}
        if sha(source/'original.bin') != snapshot['sourceSha256']:
            raise ValueError('元画像ハッシュが違います')
        for key, value in [('datasetId', snapshot['datasetId']), ('captureGroup', snapshot['captureGroup']),
                           ('sourceSha256', snapshot['sourceSha256']), ('annotationRevision', snapshot['revision']),
                           ('corners', snapshot['corners'])]:
            if manifest[key] != value:
                raise ValueError('manifestと固定GTが違います')
        if [s['label'] for s in sorted(manifest['samples'], key=lambda s: (s['row'], s['column']))] != snapshot['labels']:
            raise ValueError('固定GTのラベルが一致しません')
        shift, calibration_info = calibration(args.centers, snapshot, snapshot_path)
        for mode, offset in [('zero', [0., 0.]), ('manual', shift)]:
            name = snapshot['datasetId']+'-'+mode
            # 画像と四隅と明示的な校正値だけを推論へ渡す。GTラベルを渡さない。
            raw = run([args.jdk/'java.exe', '-cp', cp, 'CandidateProbe', source/'source.png',
                       *[v for p in snapshot['corners'] for v in p], *offset])
            (output/(name+'-probe.tsv')).write_text(raw, encoding='utf-8')
            dense, empty, baseline = [], ['unknown']*361, ['unknown']*361
            for line in raw.splitlines():
                f = line.split('\t')
                if f[0] == 'D':
                    dense.append(dict(x=float(f[1]), y=float(f[2]), state=f[3].lower(), support=float(f[4])))
                else:
                    index = int(float(f[2]))*19+int(float(f[1]))
                    (baseline if f[0] == 'B' else empty)[index] = f[3].lower()
            baseline_report = compare(manifest, baseline, 'recompiled-baseline', code_hashes)
            saved_baseline = json.loads((folder/'baseline-2048-report.json').read_bytes())
            saved_predictions = read_predictions((folder/'baseline-2048.txt').read_text(encoding='utf-8-sig'))
            if baseline_report['confusionMatrix'] != saved_baseline['confusionMatrix'] or baseline != saved_predictions:
                raise ValueError('再実行した基準値が固定結果と違います')
            candidates = aggregate(dense)
            predictions, assignments = assign(candidates, offset, empty)
            # 推論が終わってからGTを評価へ渡す。
            report = compare(manifest, predictions, 'dense-NMS-joint-conservative-'+mode, code_hashes)
            report.update(parameters=PARAMETERS, shift=offset,
                          calibration=calibration_info if mode == 'manual' else dict(kind='zero-control'),
                          annotationSha256=sha(snapshot_path), manifestSha256=sha(manifest_path),
                          inputSha256=input_hashes,
                          orientedPngSha256=sha(source/'source.png'), baselineReproduced=True,
                          baseline=dict(correct=saved_baseline['correctKnown'], wrong=saved_baseline['wrongKnown'], unknown=saved_baseline['unknownKnown']),
                          candidates=candidates, assignments=assignments,
                          transitions=[dict(row=i//19+1, column=i%19+1, baseline=b, prediction=p, truth=snapshot['labels'][i])
                                       for i, (b,p) in enumerate(zip(baseline,predictions)) if b != p])
            symbols = dict(empty='.', black='B', white='W', unknown='?')
            (output/(name+'.txt')).write_text('\n'.join(f'{r+1:02d} '+''.join(symbols[p] for p in predictions[r*19:(r+1)*19]) for r in range(19))+'\n', encoding='utf-8')
            write_json(output/(name+'-report.json'), report)
            summary.append(dict(dataset=snapshot['datasetId'], mode=mode, shift=offset,
                                correct=report['correctKnown'], wrong=report['wrongKnown'], unknown=report['unknownKnown'],
                                candidates=len(candidates), assigned=sum(e['assignedIndex'] is not None for e in assignments)))
            print(json.dumps(summary[-1]), flush=True)
        if input_hashes != {str(p.resolve().relative_to(REPO)): sha(p) for p in protected}:
            raise ValueError('評価中に入力が変わりました')
    write_json(output/'summary.json', dict(parameters=PARAMETERS, codeSha256=code_hashes, results=summary,
               scope='one-capture-group-development-with-manual-calibration-not-independent-test'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, action='append', required=True, help='固定GTのcropsフォルダ')
    parser.add_argument('--centers', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jdk', type=Path, required=True, help='JDK21のbin')
    parser.add_argument('--gradle-cache', type=Path, default=Path.home()/'.gradle/caches/modules-2/files-2.1')
    evaluate(parser.parse_args())
