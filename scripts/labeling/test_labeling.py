import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

from server import HERE, atomic_json, export_crops, make_server, prepare, project, validate_corners, validate_edit

CORNERS = [[.08, .08], [.92, .08], [.92, .92], [.08, .92]]


class LabelingTest(unittest.TestCase):
    def setUp(self):
        captures = (HERE.parents[1] / "captures").resolve()
        captures.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="labeling-test-", dir=captures)
        self.root = Path(self.temp.name).resolve()
        self.assertTrue(self.root.is_relative_to(captures))
        self.addCleanup(self.temp.cleanup)
        self.image = self.root / "fixture.png"
        Image.new("RGB", (256, 240), (185, 139, 80)).save(self.image)
        self.folder = self.root / "dataset"
        self.data = prepare(self.image, self.folder, "fixture", "synthetic-test", copy.deepcopy(CORNERS))

    def test_prepare_keeps_resolution_and_starts_without_predictions(self):
        self.assertEqual([None] * 361, self.data["labels"])
        self.assertFalse(self.data["reviewCompleted"])
        self.assertFalse(self.data["geometryReviewed"])
        with Image.open(self.folder / "source.png") as image:
            self.assertEqual((256, 240), image.size)
        self.assertEqual(self.image.read_bytes(), (self.folder / "original.bin").read_bytes())
        with self.assertRaises(FileExistsError):
            prepare(self.image, self.folder, "fixture", "synthetic-test", CORNERS)

    def test_reference_is_an_unapplied_draft_with_frozen_provenance(self):
        reviewed = dict(self.data, geometryReviewed=True, reviewCompleted=True, labels=["empty"] * 361)
        reviewed["labels"][5] = "black"
        reference = self.root / "reviewed.json"
        atomic_json(reference, reviewed)
        target = self.root / "target"
        draft = prepare(self.image, target, "target", "synthetic-test", CORNERS, reference)
        self.assertEqual([None] * 361, draft["labels"])
        self.assertFalse(draft["referenceApplied"])
        self.assertFalse(draft["reviewCompleted"])
        self.assertEqual("black", draft["referenceDraft"]["labels"][5])
        candidate = copy.deepcopy(draft)
        candidate["referenceApplied"] = True
        with self.assertRaises(ValueError):
            validate_edit(draft, candidate)
        candidate.update(geometryReviewed=True, labels=reviewed["labels"])
        edited = validate_edit(draft, candidate)
        self.assertFalse(edited["reviewCompleted"])
        with self.assertRaises(ValueError):
            export_crops(target, self.root / "unfinished")
        candidate["referenceDraft"]["annotationRevision"] += 1
        with self.assertRaises(ValueError):
            validate_edit(draft, candidate)
        edited["reviewCompleted"] = True
        atomic_json(target / "annotations.json", edited)
        export_crops(target, self.root / "export")
        manifest = json.loads((self.root / "export" / "manifest.json").read_text())
        self.assertEqual("fixture", manifest["referenceProvenance"]["datasetId"])
        self.assertNotIn("labels", manifest["referenceProvenance"])
        for invalid in (dict(reviewed, reviewCompleted=False), dict(reviewed, captureGroup="other")):
            atomic_json(reference, invalid)
            with self.assertRaises(ValueError):
                prepare(self.image, self.root / "rejected", "rejected", "synthetic-test", CORNERS, reference)
        self.assertFalse((self.root / "rejected").exists())

    def test_projection_supports_perspective_and_rejects_bad_geometry(self):
        trapezoid = [[.2, .1], [.8, .15], [.95, .9], [.05, .85]]
        validate_corners(trapezoid)
        for index, position in enumerate(((0, 0), (18, 0), (18, 18), (0, 18))):
            result = project(trapezoid, *position)
            for actual, expected in zip(result, trapezoid[index]):
                self.assertAlmostEqual(expected, actual)
        for corners in ([CORNERS[0]] * 4, [CORNERS[i] for i in (0, 2, 1, 3)],
                        [[float("nan"), .1], *CORNERS[1:]], [[-1, 0], *CORNERS[1:]]):
            with self.assertRaises(ValueError):
                validate_corners(corners)

    def test_unknown_is_separate_and_unfinished_labels_cannot_be_completed(self):
        candidate = copy.deepcopy(self.data)
        candidate["labels"][0] = "black"
        with self.assertRaises(ValueError):
            validate_edit(self.data, candidate)
        candidate["geometryReviewed"] = True
        candidate["labels"][1] = "unknown"
        self.assertEqual(["black", "unknown", None], validate_edit(self.data, candidate)["labels"][:3])
        candidate["reviewCompleted"] = True
        with self.assertRaises(ValueError):
            validate_edit(self.data, candidate)
        for bad in ("prediction", 0, {}, ["white"]):
            candidate["labels"][0] = bad
            with self.assertRaises(ValueError):
                validate_edit(self.data, candidate)

    def test_import_rejects_other_sources_and_identity_changes(self):
        for key in ("datasetId", "sourceSha256", "captureGroup", "width"):
            candidate = copy.deepcopy(self.data)
            candidate[key] = "other"
            with self.assertRaises(ValueError):
                validate_edit(self.data, candidate)

    def test_export_requires_review_and_preserves_native_crop_coordinates(self):
        with self.assertRaises(ValueError):
            export_crops(self.folder, self.root / "crops")
        data = dict(self.data, geometryReviewed=True, reviewCompleted=True, labels=["empty"] * 361)
        data["labels"][0] = "unknown"
        atomic_json(self.folder / "annotations.json", data)
        export_crops(self.folder, self.root / "crops")
        manifest = json.loads((self.root / "crops/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(361, len(manifest["samples"]))
        self.assertFalse(manifest["samples"][0]["eligibleForSupervisedClassification"])
        self.assertTrue(manifest["samples"][1]["eligibleForSupervisedClassification"])
        self.assertEqual("unassigned", manifest["split"])
        sample = manifest["samples"][180]
        left, top, right, bottom = sample["sourceBounds"]
        with Image.open(self.root / "crops" / sample["file"]) as image:
            self.assertEqual((right - left, bottom - top), image.size)
            self.assertEqual((185, 139, 80), image.getpixel((0, 0)))
        self.assertAlmostEqual(128 - left, sample["intersectionInCrop"][0])

    def test_http_save_is_durable_and_checks_origin_token_and_revision(self):
        server = make_server(self.folder)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            origin = f"http://127.0.0.1:{server.server_port}"
            result = json.load(urlopen(origin + "/api/data"))
            candidate = dict(result["data"], geometryReviewed=True)
            candidate["labels"][0] = "white"
            payload = json.dumps(dict(expectedRevision=0, data=candidate)).encode()
            headers = {"Content-Type": "application/json", "Origin": origin, "X-Label-Token": result["token"]}
            with self.assertRaises(HTTPError) as failure:
                urlopen(Request(origin + "/api/save", payload, {"Origin": origin}))
            self.assertEqual(403, failure.exception.code)
            response = json.load(urlopen(Request(origin + "/api/save", payload, headers)))
            self.assertEqual(1, response["revision"])
            saved = json.loads((self.folder / "annotations.json").read_text(encoding="utf-8"))
            self.assertEqual("white", saved["labels"][0])
            previous = json.loads((self.folder / "annotations.previous.json").read_text(encoding="utf-8"))
            self.assertIsNone(previous["labels"][0])
            with self.assertRaises(HTTPError) as conflict:
                urlopen(Request(origin + "/api/save", payload, headers))
            self.assertEqual(409, conflict.exception.code)
            self.assertEqual(saved, json.loads((self.folder / "annotations.json").read_text(encoding="utf-8")))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
