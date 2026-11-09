import tempfile
import unittest
from pathlib import Path

from review_gt import build
from server import HERE, atomic_json


class ReviewGTTest(unittest.TestCase):
    def test_rejects_superseded_unsafe_id_and_changed_gt_before_output(self):
        with tempfile.TemporaryDirectory(dir=HERE.parents[1]/'captures') as temporary:
            root = Path(temporary)
            inventory = root/'inventory.json'
            row = dict(datasetId='old')
            for rows, superseded in (([row], ['old']), ([dict(datasetId='../escape')], [])):
                atomic_json(inventory, dict(datasets=rows, supersededDatasets=superseded))
                with self.assertRaises(ValueError):
                    build(inventory, root/'output')
                self.assertFalse((root/'output').exists())
            annotation = root/'annotations.json'
            annotation.write_text('{}')
            (root/'manifest.json').write_text('{}')
            row.update(annotationFile=str(annotation), annotationSha256='incorrect', manifestSha256='incorrect')
            atomic_json(inventory, dict(datasets=[row]))
            with self.assertRaises(ValueError):
                build(inventory, root/'output')
            self.assertFalse((root/'output').exists())
