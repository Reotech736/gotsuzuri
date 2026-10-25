import unittest

from compare import compare, read_predictions


class CompareTest(unittest.TestCase):
    def manifest(self):
        return dict(datasetId="fixture", captureGroup="synthetic", sourceSha256="fixture-hash",
                    annotationRevision=1, split="unassigned",
                    samples=[dict(row=i // 19 + 1, column=i % 19 + 1, label="empty") for i in range(361)])

    def test_keeps_unknown_separate_from_wrong_and_excludes_unknown_truth(self):
        data = self.manifest()
        data["samples"][0]["label"] = "black"
        data["samples"][1]["label"] = "white"
        data["samples"][2]["label"] = "unknown"
        predictions = ["empty"] * 361
        predictions[0], predictions[1], predictions[2] = "unknown", "black", "white"
        result = compare(data, predictions, "test", "fixture")
        self.assertEqual(358, result["correctKnown"])
        self.assertEqual(1, result["wrongKnown"])
        self.assertEqual(1, result["unknownKnown"])
        self.assertEqual(1, result["excludedGroundTruthUnknown"])
        self.assertEqual(dict(row=1, column=1, truth="black", prediction="unknown"), result["differences"][0])

    def test_rejects_missing_or_duplicate_prediction_rows(self):
        lines = [f"{row:02d} " + "." * 19 for row in range(1, 20)]
        self.assertEqual(["empty"] * 361, read_predictions("\n".join(lines)))
        for text in ("\n".join(lines[:-1]), "\n".join(lines + [lines[0]]), "\n".join(lines[:-1] + ["19 BBB"])):
            with self.assertRaises(ValueError):
                read_predictions(text)

    def test_does_not_depend_on_manifest_sample_order(self):
        data = self.manifest()
        data["samples"][0]["label"] = "black"
        data["samples"].reverse()
        result = compare(data, ["black"] + ["empty"] * 360, "test", "fixture")
        self.assertEqual(361, result["correctKnown"])

    def test_rejects_duplicate_ground_truth_coordinates(self):
        data = self.manifest()
        data["samples"][-1] = data["samples"][0]
        with self.assertRaises(ValueError):
            compare(data, ["empty"] * 361, "test", "fixture")


if __name__ == "__main__":
    unittest.main()
