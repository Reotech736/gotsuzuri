"""PC内だけで使う静止画像の正解ラベル作成。画像・ラベルはcaptures配下へ。"""
import argparse
import hashlib
import json
import math
import secrets
import shutil
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageOps

STATES = {None, "empty", "black", "white", "unknown"}
HERE = Path(__file__).resolve().parent


def project(corners, column, row):
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = corners
    dx1, dx2, dx3 = x1 - x2, x3 - x2, x0 - x1 + x2 - x3
    dy1, dy2, dy3 = y1 - y2, y3 - y2, y0 - y1 + y2 - y3
    if abs(dx3) < 1e-10 and abs(dy3) < 1e-10:
        g = h = 0.0
    else:
        det = dx1 * dy2 - dx2 * dy1
        if abs(det) < 1e-10:
            raise ValueError("退化した四隅です")
        g = (dx3 * dy2 - dx2 * dy3) / det
        h = (dx1 * dy3 - dx3 * dy1) / det
    u, v = column / 18, row / 18
    d = g * u + h * v + 1
    if d <= 1e-10:
        raise ValueError("射影できない四隅です")
    return (((x1 - x0 + g * x1) * u + (x3 - x0 + h * x3) * v + x0) / d,
            ((y1 - y0 + g * y1) * u + (y3 - y0 + h * y3) * v + y0) / d)


def validate_corners(corners):
    if not isinstance(corners, list) or len(corners) != 4:
        raise ValueError("四隅は左上→右上→右下→左下の4点です")
    for point in corners:
        if not isinstance(point, list) or len(point) != 2 or any(
                type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in point):
            raise ValueError("四隅は画像内の有限な正規化座標です")
    for i in range(4):
        a, b, c = corners[i], corners[(i + 1) % 4], corners[(i + 2) % 4]
        if (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) <= 1e-8:
            raise ValueError("四隅の交差・重複・逆順を修正してください")
    for c, r in ((0, 0), (18, 0), (18, 18), (0, 18)):
        project(corners, c, r)


def atomic_json(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def prepare(source, output, dataset_id, group_id, corners):
    validate_corners(corners)
    output = output.resolve()
    # 個人画像を誤って公開対象へ生成しない。Git管理外のcapturesだけを出力先にする。
    captures = HERE.parents[1] / "captures"
    if not output.is_relative_to(captures.resolve()):
        raise ValueError("出力先はこのリポジトリのcaptures配下を指定してください")
    output.mkdir(parents=True, exist_ok=False)
    original_bytes = source.read_bytes()
    source_hash = hashlib.sha256(original_bytes).hexdigest()
    shutil.copyfile(source, output / "original.bin")
    with Image.open(source) as original:
        oriented = ImageOps.exif_transpose(original).convert("RGB")
        oriented.save(output / "source.png")  # 再縮小・JPEG再圧縮なし。
        width, height = oriented.size
    data = dict(schemaVersion=1, datasetId=dataset_id, captureGroup=group_id,
                sourceSha256=source_hash, width=width, height=height,
                coordinateConvention="image-top-left-row-column-1-based",
                corners=corners, geometryReviewed=False, reviewCompleted=False, labels=[None] * 361,
                revision=0, savedAt=None)
    atomic_json(output / "annotations.json", data)
    return data


def validate_edit(current, candidate):
    if not isinstance(candidate, dict):
        raise ValueError("ラベルJSONの形式が違います")
    for key in ("schemaVersion", "datasetId", "captureGroup", "sourceSha256", "width", "height", "coordinateConvention"):
        if candidate.get(key) != current[key]:
            raise ValueError("別の画像・データセットのラベルは取り込めません")
    validate_corners(candidate.get("corners"))
    labels = candidate.get("labels")
    if not isinstance(labels, list) or len(labels) != 361 or any(
            value is not None and (not isinstance(value, str) or value not in STATES) for value in labels):
        raise ValueError("361個の空・黒・白・判別不能・未分類のみを保存できます")
    if type(candidate.get("geometryReviewed")) is not bool:
        raise ValueError("位置合わせの確認状態が不正です")
    if not candidate["geometryReviewed"] and any(value is not None for value in labels):
        raise ValueError("ラベルを付ける前に位置合わせを確認してください")
    completed = candidate.get("reviewCompleted")
    if type(completed) is not bool or (completed and (not candidate["geometryReviewed"] or None in labels)):
        raise ValueError("未分類の交点が残っています")
    return dict(current, corners=candidate["corners"], geometryReviewed=candidate["geometryReviewed"],
                reviewCompleted=completed, labels=labels)


def export_crops(folder, output):
    data = json.loads((folder / "annotations.json").read_text(encoding="utf-8"))
    validate_edit(data, data)
    if not data["reviewCompleted"]:
        raise ValueError("本人による分類の完了後に書き出してください")
    captures = (HERE.parents[1] / "captures").resolve()
    if not output.resolve().is_relative_to(captures):
        raise ValueError("出力先はcaptures配下を指定してください")
    output.mkdir(parents=True, exist_ok=False)
    samples = []
    with Image.open(folder / "source.png") as image:
        for index, label in enumerate(data["labels"]):
            column, row = index % 19, index // 19
            x, y = project(data["corners"], column, row)
            x *= data["width"]
            y *= data["height"]
            neighbors = [project(data["corners"], max(0, min(18, column + dx)), max(0, min(18, row + dy)))
                         for dx in (-1.25, 1.25) for dy in (-1.25, 1.25)]
            radius = max(16, *(math.hypot(px * data["width"] - x, py * data["height"] - y) for px, py in neighbors))
            bounds = [max(0, math.floor(x - radius)), max(0, math.floor(y - radius)),
                      min(data["width"], math.ceil(x + radius)), min(data["height"], math.ceil(y + radius))]
            filename = f"r{row + 1:02d}-c{column + 1:02d}.png"
            image.crop(bounds).save(output / filename)
            samples.append(dict(row=row + 1, column=column + 1, label=label, file=filename,
                                sourceBounds=bounds, intersectionInCrop=[x - bounds[0], y - bounds[1]],
                                eligibleForSupervisedClassification=label in ("empty", "black", "white")))
    atomic_json(output / "manifest.json", dict(schemaVersion=1, datasetId=data["datasetId"],
                captureGroup=data["captureGroup"], sourceSha256=data["sourceSha256"],
                annotationRevision=data["revision"], corners=data["corners"],
                split="unassigned", samples=samples))


def make_server(folder, port=0):
    folder = folder.resolve()
    path = folder / "annotations.json"
    current = json.loads(path.read_text(encoding="utf-8"))
    token = secrets.token_urlsafe(24)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # 個人のパスやラベルをログへ出さない。

        def response(self, status, body, kind="application/json; charset=utf-8"):
            encoded = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(encoded)

        def valid_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.valid_host():
                return self.response(403, {"error": "local host only"})
            route = urlparse(self.path).path
            assets = {"/": (HERE / "index.html", "text/html; charset=utf-8"),
                      "/app.js": (HERE / "app.js", "text/javascript; charset=utf-8"),
                      "/style.css": (HERE / "style.css", "text/css; charset=utf-8"),
                      "/source.png": (folder / "source.png", "image/png")}
            if route in assets:
                file, kind = assets[route]
                return self.response(200, file.read_bytes(), kind)
            if route == "/api/data":
                with lock:
                    return self.response(200, {"data": current, "token": token})
            return self.response(404, {"error": "not found"})

        def do_POST(self):
            nonlocal current
            expected_origin = f"http://127.0.0.1:{self.server.server_port}"
            if not self.valid_host() or self.headers.get("Origin") != expected_origin or self.headers.get("X-Label-Token") != token:
                return self.response(403, {"error": "保存元が一致しません"})
            if self.path != "/api/save":
                return self.response(404, {"error": "not found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length < 65536:
                    raise ValueError("保存データが大きすぎます")
                payload = json.loads(self.rfile.read(length))
                with lock:
                    if type(payload.get("expectedRevision")) is not int or payload["expectedRevision"] != current["revision"]:
                        return self.response(409, {"error": "別の画面で更新されました。JSONを退避し、画面を再読み込みしてください"})
                    updated = validate_edit(current, payload.get("data"))
                    updated["revision"] = current["revision"] + 1
                    updated["savedAt"] = datetime.now(timezone.utc).isoformat()
                    shutil.copyfile(path, folder / "annotations.previous.json")
                    atomic_json(path, updated)
                    current = updated
                    return self.response(200, {"revision": updated["revision"], "savedAt": updated["savedAt"]})
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                return self.response(400, {"error": "保存内容が不正です。ラベルと位置合わせを確認してください"})
            except OSError:
                return self.response(500, {"error": "ファイルへ保存できません。JSONをダウンロードして退避してください"})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(folder, port, ready_file):
    server = make_server(folder, port)
    url = f"http://127.0.0.1:{server.server_port}/"
    ready_file.write_text(url, encoding="utf-8")
    print(url, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("prepare")
    make.add_argument("--image", type=Path, required=True)
    make.add_argument("--output", type=Path, required=True)
    make.add_argument("--id", required=True)
    make.add_argument("--group", required=True)
    make.add_argument("--corners", type=json.loads, required=True)
    run = commands.add_parser("serve")
    run.add_argument("--data", type=Path, required=True)
    run.add_argument("--port", type=int, default=0)
    run.add_argument("--ready-file", type=Path, required=True)
    export = commands.add_parser("export")
    export.add_argument("--data", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.image, args.output, args.id, args.group, args.corners)
        print("未分類361点で作成しました。")
    elif args.command == "serve":
        serve(args.data, args.port, args.ready_file)
    else:
        export_crops(args.data, args.output)
        print("原寸周辺画像361枚とmanifest.jsonを書き出しました。")
