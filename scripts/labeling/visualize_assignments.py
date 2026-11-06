"""保存済みの候補・割当・GTを読み取り専用のローカル画面へ書き出す。再推論しない。"""
import argparse
import base64
import gzip
import json
import re
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image

from assign_candidates import sha
from centers import validate_centers
from compare import compare, read_predictions
from server import project, validate_edit

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CAPTURES = REPO / 'captures'


def within_captures(path):
    path = path.resolve()
    if not path.is_relative_to(CAPTURES.resolve()):
        raise ValueError('入出力はこのリポジトリのcaptures配下にしてください')
    return path


def image_point(corners, column, row):
    # 保存された補正座標は盤外になり得る。表示のために盤外へ射影しない。
    if not (0 <= column <= 18 and 0 <= row <= 18):
        return None
    return list(project(corners, column, row))


def load_view(results, centers_path):
    results, centers_path = within_captures(results), within_captures(centers_path)
    summary = json.loads((results / 'summary.json').read_bytes())
    centers = json.loads(centers_path.read_bytes())
    validate_centers(centers, centers)
    if not centers['reviewCompleted']:
        raise ValueError('中心の本人確認が未完了です')
    views, images, inputs = [], {}, {str(centers_path.relative_to(REPO)): sha(centers_path)}
    for item in summary['results']:
        dataset, mode = item['dataset'], item['mode']
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', dataset) or mode not in ('zero', 'manual'):
            raise ValueError('データセットIDまたは比較条件が不正です')
        key = dataset + '-' + mode
        report_path = results / (key + '-report.json')
        prediction_path = results / (key + '.txt')
        report = json.loads(report_path.read_bytes())
        crops = CAPTURES / 'labeling' / (dataset + '-crops')
        snapshot_path = crops / 'annotations-reviewed.json'
        gt = json.loads(snapshot_path.read_bytes())
        manifest = json.loads((crops / 'manifest.json').read_bytes())
        validate_edit(gt, gt)
        if not gt['reviewCompleted'] or gt['datasetId'] != dataset:
            raise ValueError('固定GTが未完了、または別画像です')
        if report['annotationSha256'] != sha(snapshot_path) or report['manifestSha256'] != sha(crops / 'manifest.json'):
            raise ValueError('結果と固定GTのハッシュが一致しません')
        if report['datasetId'] != dataset or report['annotationRevision'] != gt['revision'] or report['sourceSha256'] != gt['sourceSha256']:
            raise ValueError('結果と固定GTの出典が違います')
        for relative, digest in report['inputSha256'].items():
            path = within_captures(REPO / relative)
            if sha(path) != digest:
                raise ValueError('評価時から入力が変わっています: ' + path.name)
            inputs[str(path.relative_to(REPO))] = digest
        if mode == 'manual' and report['calibration']['kind'] == 'manual-per-image-constant-translation':
            if report['calibration']['studySha256'] != sha(centers_path):
                raise ValueError('校正に使った中心の出典が違います')
        predictions = read_predictions(prediction_path.read_text(encoding='utf-8-sig'))
        evaluation = compare(manifest, predictions, 'view-validation', 'saved-results')
        if evaluation['confusionMatrix'] != report['confusionMatrix'] or any(
                report[k] != evaluation[k] for k in ('correctKnown', 'wrongKnown', 'unknownKnown')):
            raise ValueError('保存された予測と比較結果が違います')
        if (item['correct'], item['wrong'], item['unknown']) != tuple(report[k] for k in ('correctKnown', 'wrongKnown', 'unknownKnown')):
            raise ValueError('summaryと比較結果が違います')
        image = within_captures(CAPTURES / 'labeling' / dataset / 'source.png')
        if sha(image) != report['orientedPngSha256']:
            raise ValueError('表示画像のハッシュが違います')
        images[dataset] = image
        assignments = {a['candidateId']: a for a in report['assignments']}
        if len(assignments) != len(report['candidates']) or set(assignments) != {c['id'] for c in report['candidates']}:
            raise ValueError('候補と対応のIDが一致しません')
        assigned = [a['assignedIndex'] for a in assignments.values() if a['assignedIndex'] is not None]
        if len(assigned) != len(set(assigned)) or any(type(i) is not int or not 0 <= i < 361 for i in assigned):
            raise ValueError('一対一対応の記録が不正です')
        candidates = []
        for c in report['candidates']:
            a = assignments[c['id']]
            candidates.append(dict(c, image=image_point(gt['corners'], c['x'], c['y']), assignment=a,
                                   correctedImage=image_point(gt['corners'], *a['correctedBoardCenter']),
                                   members=[dict(m, image=image_point(gt['corners'], m['x'], m['y'])) for m in c['members']]))
        baseline = predictions.copy()
        for t in report['transitions']:
            i = (t['row'] - 1) * 19 + t['column'] - 1
            baseline[i] = t['baseline']
        sites = [dict(index=i, row=i//19+1, column=i%19+1, image=image_point(gt['corners'], i%19, i//19),
                      truth=gt['labels'][i], prediction=predictions[i], baseline=baseline[i]) for i in range(361)]
        manual = []
        for task, center in zip(centers['tasks'], centers['centers']):
            if task['datasetId'] != dataset or center['status'] != 'marked':
                continue
            if (task['annotationSha256'] != sha(snapshot_path) or task['sourceSha256'] != gt['sourceSha256']
                    or task['sourceWidth'] != gt['width'] or task['sourceHeight'] != gt['height']):
                raise ValueError('中心と固定GTの出典が違います')
            for name, hash_key in [('file', 'cropSha256'), ('referenceFile', 'referenceSha256')]:
                path = within_captures(centers_path.parent/task[name])
                if sha(path) != task[hash_key]:
                    raise ValueError('中心の切り出しまたは参照画像が変わっています')
                inputs[str(path.relative_to(REPO))] = sha(path)
            manual.append(dict(id=task['id'], row=task['row'], column=task['column'],
                               image=[(task['sourceBounds'][0]+center['centerInCrop'][0])/task['sourceWidth'],
                                      (task['sourceBounds'][1]+center['centerInCrop'][1])/task['sourceHeight']]))
        views.append(dict(key=key, dataset=dataset, mode=mode, width=gt['width'], height=gt['height'],
                          imageFile=dataset+'-preview.jpg', originalFile=dataset+'.png', sites=sites, candidates=candidates, centers=manual,
                          shift=report['shift'], calibration=report['calibration'],
                          correct=report['correctKnown'], wrong=report['wrongKnown'], unknown=report['unknownKnown'],
                          baseline=report['baseline'], revision=gt['revision'], captureGroup=gt['captureGroup'],
                          reportSha256=sha(report_path)))
        for path in (report_path, prediction_path, snapshot_path, crops/'manifest.json', image):
            inputs[str(path.relative_to(REPO))] = sha(path)
    return dict(views=views, inputSha256=inputs), images


def build(results, centers, output):
    output = within_captures(output)
    data, images = load_view(results, centers)
    output.mkdir(parents=True, exist_ok=False)
    for source, name in [('assignments.html', 'index.html'), ('assignments.js', 'assignments.js')]:
        shutil.copyfile(HERE/source, output/name)
    data['previews'] = {}
    for dataset, path in images.items():
        shutil.copyfile(path, output/(dataset+'.png'))  # 原寸・元PNGのバイト列を維持。
        with Image.open(path) as original:
            preview = original.convert('RGB')
            preview.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
            preview.save(output/(dataset+'-preview.jpg'), quality=95, subsampling=0)
        data['previews'][dataset] = 'data:image/jpeg;base64,' + base64.b64encode((output/(dataset+'-preview.jpg')).read_bytes()).decode('ascii')
    payload = json.dumps(data, ensure_ascii=True, allow_nan=False)
    (output/'view-data.json').write_text(payload+'\n', encoding='utf-8')
    (output/'provenance.json').write_text(json.dumps(dict(inputSha256=data['inputSha256'],
        toolSha256={name: sha(HERE/name) for name in ('visualize_assignments.py', 'assignments.html', 'assignments.js')}), indent=2)+'\n', encoding='utf-8')
    for relative, digest in data['inputSha256'].items():
        if sha(REPO/relative) != digest:
            raise ValueError('書き出し中に入力が変わりました')
    return data


def make_server(folder, port=0):
    folder = within_captures(folder)
    allowed = {p.name: p for p in folder.iterdir() if (p.suffix in ('.html', '.js', '.png', '.jpg') or p.name == 'view-data.json') and p.is_file()}
    types = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.png': 'image/png', '.jpg': 'image/jpeg', '.json': 'application/json; charset=utf-8'}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *_):
            pass

        def do_POST(self):
            self.close_connection = True
            # 小さいリクエスト本文を読み切ってから拒否し、Windowsの接続リセットを避ける。
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                self.send_error(400)
                return
            if not 0 <= length <= 65536:
                self.send_error(413)
                return
            self.rfile.read(length)
            self.send_error(405, 'Read-only viewer')

        def do_GET(self):
            if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
                self.send_error(403)
                return
            name = urlsplit(self.path).path
            name = 'index.html' if name == '/' else name.removeprefix('/')
            if name not in allowed:
                self.send_error(404)
                return
            raw = allowed[name].read_bytes()
            compressed = allowed[name].suffix in ('.html', '.js', '.json') and 'gzip' in self.headers.get('Accept-Encoding', '')
            if compressed:
                raw = gzip.compress(raw)
            self.send_response(200)
            self.send_header('Content-Type', types[allowed[name].suffix])
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            if compressed:
                self.send_header('Content-Encoding', 'gzip')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def serve(folder, port=0):
    folder = within_captures(folder)
    server = make_server(folder, port)
    url = f'http://127.0.0.1:{server.server_port}/'
    (folder/'server-url.txt').write_text(url, encoding='utf-8')
    print(url, flush=True)
    server.serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    export = commands.add_parser('build')
    export.add_argument('--results', type=Path, required=True)
    export.add_argument('--centers', type=Path, required=True)
    export.add_argument('--output', type=Path, required=True)
    start = commands.add_parser('serve')
    start.add_argument('--data', type=Path, required=True)
    start.add_argument('--port', type=int, default=0, help='省略時は空きポートを選ぶ。再起動時に現在のURLを保つ場合に指定')
    args = parser.parse_args()
    if args.command == 'build':
        data = build(args.results, args.centers, args.output)
        print(f"{len(data['views'])}条件を書き出しました。GT・画像・予測は変更していません。")
    else:
        serve(args.data, args.port)
