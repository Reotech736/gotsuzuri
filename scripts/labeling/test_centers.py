import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

from centers import prepare_centers, validate_centers
from server import HERE, atomic_json, export_crops, make_server, prepare


class CenterTest(unittest.TestCase):
    def setUp(self):
        captures = (HERE.parents[1] / "captures").resolve()
        self.temp = tempfile.TemporaryDirectory(prefix="center-test-", dir=captures)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.png"
        Image.new("RGB", (400, 400), (185, 139, 80)).save(self.source)
        self.originals = []
        self.exports = []
        for name in ("reference", "low", "high"):
            folder = self.root / name
            data = prepare(self.source, folder, name, "synthetic", [[.1,.1],[.9,.1],[.9,.9],[.1,.9]])
            data.update(geometryReviewed=True, reviewCompleted=True, labels=["empty"] * 361)
            data["labels"][21:25] = ["black", "black", "white", "white"]
            atomic_json(folder / "annotations.json", data)
            output = self.root / (name + "-crops")
            export_crops(folder, output)
            snapshot = (folder / "annotations.json").read_bytes()
            (output / "annotations-reviewed.json").write_bytes(snapshot)
            self.originals.append((folder / "annotations.json", snapshot))
            self.exports.append(output)
        self.folder = self.root / "study"
        self.data = prepare_centers(self.exports[1:], self.exports[0], self.folder, "study")

    def test_prepare_keeps_gt_and_starts_without_centers(self):
        self.assertEqual(8, len(self.data["tasks"]))
        self.assertTrue(all(e == dict(status="pending", centerInCrop=None) for e in self.data["centers"]))
        self.assertFalse(self.data["reviewCompleted"])
        self.assertEqual(["black", "black", "white", "white"] * 2, [t["label"] for t in self.data["tasks"]])
        for path, snapshot in self.originals:
            self.assertEqual(snapshot, path.read_bytes())
        with self.assertRaises(ValueError):
            prepare_centers(self.exports[1:], self.exports[0], HERE / "invalid-output", "invalid")

    def test_validation_preserves_identity_and_requires_observable_points_in_image(self):
        candidate = copy.deepcopy(self.data)
        candidate["reviewCompleted"] = True
        with self.assertRaises(ValueError):
            validate_centers(self.data, candidate)
        candidate["centers"] = [dict(status="unobservable", centerInCrop=None) for _ in range(8)]
        self.assertTrue(validate_centers(self.data, candidate)["reviewCompleted"])
        candidate["centers"][0] = dict(status="marked", centerInCrop=[0,0])
        validate_centers(self.data, candidate)
        for bad in ([float("nan"),1], [True,1], [-1,1], [self.data["tasks"][0]["width"],0], None):
            candidate["centers"][0]["centerInCrop"] = bad
            with self.assertRaises(ValueError):
                validate_centers(self.data, candidate)
        candidate["centers"][0] = dict(status="unobservable", centerInCrop=[1,1])
        with self.assertRaises(ValueError):
            validate_centers(self.data, candidate)
        candidate = copy.deepcopy(self.data)
        candidate["tasks"][0]["annotationRevision"] += 1
        with self.assertRaises(ValueError):
            validate_centers(self.data, candidate)

    def test_http_saves_centers_without_writing_gt(self):
        server = make_server(self.folder)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            origin = f"http://127.0.0.1:{server.server_port}"
            result = json.load(urlopen(origin + "/api/data"))
            self.assertIn(b"target", urlopen(origin + "/").read())
            self.assertTrue(urlopen(origin + "/crop-01.png").read().startswith(b"\x89PNG"))
            with self.assertRaises(HTTPError):
                urlopen(origin + "/source.png")
            data = result["data"]
            data["centers"][0] = dict(status="marked", centerInCrop=[10,11])
            payload = json.dumps(dict(expectedRevision=0, data=data)).encode()
            headers = {"Origin": origin, "X-Label-Token": result["token"], "Content-Type": "application/json"}
            saved = json.load(urlopen(Request(origin + "/api/save", payload, headers)))
            self.assertEqual(1, saved["revision"])
            on_disk = json.loads((self.folder / "annotations.json").read_text(encoding="utf-8"))
            self.assertEqual([10,11], on_disk["centers"][0]["centerInCrop"])
            self.assertFalse(on_disk["reviewCompleted"])
            with self.assertRaises(HTTPError) as conflict:
                urlopen(Request(origin + "/api/save", payload, headers))
            self.assertEqual(409, conflict.exception.code)
            for path, snapshot in self.originals:
                self.assertEqual(snapshot, path.read_bytes())
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
