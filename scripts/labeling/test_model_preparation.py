import unittest

from prepare_model_experiment import make_folds


class ModelPreparationTest(unittest.TestCase):
    def rows(self):
        return [dict(datasetId=d, captureGroup=g, role=role, sourceSha256=f'{i:064x}')
                for i,(d,g,role) in enumerate([
                    ('old-top','old','development'),('old-low','old','development'),
                    ('a-top','a','development'),('b-top','b','development'),
                    ('c-top','c','reserved-final-check'),('c-fixed','c','reserved-final-check')])]

    def test_keeps_same_arrangement_together_and_excludes_reserved(self):
        development,reserved,folds = make_folds(self.rows())
        self.assertEqual((4,2,3),(len(development),len(reserved),len(folds)))
        for fold in folds:
            train,validation = map(set,(fold['trainDatasets'],fold['validationDatasets']))
            self.assertFalse(train & validation)
            self.assertFalse({'c-top','c-fixed'} & (train|validation))
            self.assertEqual({'old-top','old-low','a-top','b-top'},train|validation)
            self.assertEqual('old-top' in validation,'old-low' in validation)

    def test_rejects_duplicate_ids_and_unknown_roles(self):
        for changed in ('duplicate','role'):
            rows = self.rows()
            if changed=='duplicate': rows[-1]['datasetId']=rows[0]['datasetId']
            else: rows[-1]['role']='test-maybe'
            with self.assertRaises(ValueError): make_folds(rows)

    def test_rejects_reserved_group_or_image_in_development(self):
        for field in ('captureGroup','sourceSha256'):
            rows=self.rows();rows[-1][field]=rows[0][field]
            with self.assertRaises(ValueError): make_folds(rows)

    def test_rejects_too_few_development_groups(self):
        rows=self.rows();rows[3]['captureGroup']='a'
        with self.assertRaises(ValueError): make_folds(rows)

    def test_rejects_same_image_in_different_development_groups(self):
        rows=self.rows();rows[2]['sourceSha256']=rows[0]['sourceSha256']
        with self.assertRaises(ValueError): make_folds(rows)
