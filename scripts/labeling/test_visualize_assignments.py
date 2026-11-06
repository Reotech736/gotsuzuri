import gzip
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

import visualize_assignments as viewer
from assign_candidates import sha
from compare import compare
from server import atomic_json, prepare


class ViewerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='viewer-test-', dir=viewer.CAPTURES)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.patch = patch.object(viewer, 'CAPTURES', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.source = self.root/'labeling/fixture'
        self.source.parent.mkdir()
        image = self.root/'input.png'
        Image.new('RGB', (200, 160), (185, 139, 80)).save(image)
        gt = prepare(image, self.source, 'fixture', 'synthetic', [[.1,.1],[.9,.1],[.9,.9],[.1,.9]])
        gt.update(labels=['empty']*361, geometryReviewed=True, reviewCompleted=True)
        atomic_json(self.source/'annotations.json', gt)
        self.crops = self.root/'labeling/fixture-crops'
        self.crops.mkdir()
        atomic_json(self.crops/'annotations-reviewed.json', gt)
        manifest = dict(datasetId='fixture', captureGroup='synthetic', sourceSha256=gt['sourceSha256'],
                        annotationRevision=0, samples=[dict(row=i//19+1, column=i%19+1, label='empty') for i in range(361)])
        atomic_json(self.crops/'manifest.json', manifest)
        self.centers = self.root/'centers.json'
        atomic_json(self.centers, dict(schemaVersion=1, kind='stone-center-study', datasetId='fixture-centers',
            sourceSha256='fixture', tasks=[], centers=[], coordinateConvention='native-crop-pixels-x-right-y-down', reviewCompleted=True))
        self.results = self.root/'results'
        self.results.mkdir()
        predictions = ['empty']*361
        predictions[21] = 'black'
        self.report = compare(manifest, predictions, 'synthetic', 'fixture')
        self.report.update(annotationSha256=sha(self.crops/'annotations-reviewed.json'),
            manifestSha256=sha(self.crops/'manifest.json'), orientedPngSha256=sha(self.source/'source.png'),
            inputSha256={str((self.source/'source.png').relative_to(viewer.REPO)):sha(self.source/'source.png')},
            candidates=[dict(id=0, x=2., y=1., state='black', support=1., members=[dict(x=2.,y=1.,state='black',support=1.)]),
                        dict(id=1, x=3.5, y=2., state='white', support=.8, members=[])],
            assignments=[dict(candidateId=0, assignedIndex=21, correctedBoardCenter=[2.,1.], reason='assigned', distance=0., alternatives=[]),
                         dict(candidateId=1, assignedIndex=None, correctedBoardCenter=[19.,2.], reason='outside-gate', distance=1., alternatives=[])],
            transitions=[dict(row=2,column=3,baseline='empty',prediction='black',truth='empty')],
            shift=[0.,0.],calibration=dict(kind='zero-control'),baseline=dict(correct=361,wrong=0,unknown=0))
        self.report_path = self.results/'fixture-zero-report.json'
        atomic_json(self.report_path, self.report)
        (self.results/'fixture-zero.txt').write_text('\n'.join(f'{r+1:02d} '+''.join('B' if p=='black' else '.' for p in predictions[r*19:(r+1)*19]) for r in range(19)), encoding='utf-8')
        atomic_json(self.results/'summary.json', dict(results=[dict(dataset='fixture',mode='zero',correct=360,wrong=1,unknown=0)]))

    def test_projection_uses_image_coordinate_and_keeps_outside_unknown(self):
        data, _ = viewer.load_view(self.results, self.centers)
        view = data['views'][0]
        self.assertAlmostEqual(.1, view['sites'][0]['image'][0])
        self.assertAlmostEqual(.9, view['sites'][-1]['image'][1])
        self.assertEqual(view['sites'][21]['image'], view['candidates'][0]['image'])
        self.assertIsNone(view['candidates'][1]['correctedImage'])
        self.assertEqual('empty', view['sites'][21]['baseline'])
        self.assertEqual('black', view['sites'][21]['prediction'])

    def test_build_preserves_input_bytes_and_native_png(self):
        paths = list(self.source.iterdir())+[self.report_path,self.centers]
        before = {p:sha(p) for p in paths}
        output = self.root/'output'
        viewer.build(self.results,self.centers,output)
        self.assertEqual(before,{p:sha(p) for p in paths})
        self.assertEqual(sha(self.source/'source.png'),sha(output/'fixture.png'))
        self.assertTrue((output/'fixture-preview.jpg').exists())
        payload = json.loads((output/'view-data.json').read_bytes())
        self.assertEqual(361,len(payload['views'][0]['sites']))
        with self.assertRaises(FileExistsError):
            viewer.build(self.results,self.centers,output)
        with self.assertRaises(ValueError):
            viewer.build(self.results,self.centers,viewer.HERE/'invalid-output')

    def test_reject_changed_source_and_snapshot(self):
        with (self.source/'source.png').open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaises(ValueError):
            viewer.load_view(self.results,self.centers)

    def test_reject_prediction_report_disagreement(self):
        self.report['correctKnown'] = 361
        atomic_json(self.report_path,self.report)
        with self.assertRaises(ValueError):
            viewer.load_view(self.results,self.centers)

    def test_reject_duplicate_assignment_and_path_escape(self):
        self.report['assignments'][1]['assignedIndex'] = 21
        atomic_json(self.report_path,self.report)
        with self.assertRaises(ValueError):
            viewer.load_view(self.results,self.centers)
        with self.assertRaises(ValueError):
            viewer.within_captures(self.root/'..'/'outside')

    def test_http_only_serves_view_assets_and_never_saves(self):
        output = self.root/'http'
        viewer.build(self.results,self.centers,output)
        server = viewer.make_server(output)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            origin = f'http://127.0.0.1:{server.server_port}'
            self.assertEqual(200,urlopen(origin+'/').status)
            request = Request(origin+'/view-data.json',headers={'Accept-Encoding':'gzip'})
            response = urlopen(request)
            self.assertEqual(361,len(json.loads(gzip.decompress(response.read()))['views'][0]['sites']))
            for path in ('/provenance.json','/../centers.json','/%2e%2e/centers.json'):
                with self.assertRaises(HTTPError) as error:
                    urlopen(origin+path)
                self.assertEqual(404,error.exception.code)
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(origin+'/',headers={'Host':'example.com'}))
            self.assertEqual(403,error.exception.code)
            before=sha(output/'view-data.json')
            with self.assertRaises(HTTPError):
                urlopen(Request(origin+'/view-data.json',data=b'overwrite',method='POST'))
            self.assertEqual(before,sha(output/'view-data.json'))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
