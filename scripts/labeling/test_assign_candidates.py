import math
import unittest

from assign_candidates import aggregate, assign, inverse
from server import project


def sample(x, y, state='black', support=1.):
    return dict(x=x, y=y, state=state, support=support)


def candidate(number, x, y, state='black', mixed=False):
    return dict(id=number, x=x, y=y, state=state, mixed=mixed)


class AssignmentTest(unittest.TestCase):
    def test_projection_round_trip_including_image_edges(self):
        for corners in ([[0., 0.], [1., 0.], [1., 1.], [0., 1.]],
                        [[.2, .1], [.7, .15], [.95, .9], [.05, .8]]):
            for c, r in ((0, 0), (18, 18), (0, 18), (18, 0), (2.7, 8.6)):
                actual = inverse(corners, *project(corners, c, r))
                self.assertAlmostEqual(c, actual[0], places=10)
                self.assertAlmostEqual(r, actual[1], places=10)

    def test_aggregate_same_stone_once_and_keep_neighbor(self):
        samples = [sample(2, 2), sample(2.2, 2, support=.9), sample(3, 2, 'white')]
        result = aggregate(samples)
        self.assertEqual(2, len(result))
        self.assertEqual(3, sum(len(c['members']) for c in result))
        predictions, trace = assign(result, [0, 0], ['empty']*361)
        self.assertEqual(['black', 'white'], predictions[40:42])
        self.assertEqual(2, len({e['assignedIndex'] for e in trace}))

    def test_nms_does_not_chain_adjacent_stones(self):
        result = aggregate([sample(2, 2), sample(2.4, 2), sample(2.8, 2)])
        self.assertEqual(2, len(result))

    def test_manual_translation_recovers_original_row_without_double_count(self):
        predictions, trace = assign([candidate(0, 2, .2)], [0, -.8], ['empty']*361)
        self.assertEqual('black', predictions[21])
        self.assertEqual('empty', predictions[2])
        self.assertEqual(1, predictions.count('black'))
        self.assertEqual(21, trace[0]['assignedIndex'])

    def test_midpoint_stays_unassigned_and_both_sites_unknown(self):
        predictions, trace = assign([candidate(0, 2.5, 2)], [0, 0], ['empty']*361)
        self.assertEqual(['unknown', 'unknown'], predictions[40:42])
        self.assertEqual('ambiguous-sites', trace[0]['reason'])
        self.assertIsNone(trace[0]['assignedIndex'])

    def test_two_candidates_cannot_claim_same_site(self):
        predictions, trace = assign([candidate(0, 2, 2), candidate(1, 2.1, 2, 'white')],
                                    [0, 0], ['empty']*361)
        self.assertEqual('unknown', predictions[40])
        self.assertTrue(all(e['assignedIndex'] is None for e in trace))

    def test_mixed_candidate_blocks_a_confident_rival(self):
        predictions, trace = assign([candidate(0, 2, 2), candidate(1, 2.1, 2, mixed=True)],
                                    [0, 0], ['empty']*361)
        self.assertEqual('unknown', predictions[40])
        self.assertTrue(all(e['assignedIndex'] is None for e in trace))

    def test_color_conflict_inside_one_cluster_is_not_forced(self):
        clusters = aggregate([sample(2, 2), sample(2.2, 2, 'white')])
        predictions, trace = assign(clusters, [0, 0], ['empty']*361)
        self.assertEqual('unknown', predictions[40])
        self.assertEqual('mixed-colors', trace[0]['reason'])

    def test_out_of_gate_and_clipped_empty_evidence_remain_unknown(self):
        predictions, trace = assign([candidate(0, 0, 0)], [0, 1], ['unknown']*361)
        self.assertEqual('outside-gate', trace[0]['reason'])
        self.assertEqual(361, predictions.count('unknown'))
        # 画像端の見えている候補は通常通り一度だけ対応できる。
        predictions, _ = assign([candidate(0, 18, 18)], [0, 0], ['unknown']*361)
        self.assertEqual('black', predictions[-1])

    def test_missing_candidates_do_not_turn_unknown_into_empty(self):
        predictions, _ = assign([], [0, 0], ['unknown']*360+['empty'])
        self.assertEqual(360, predictions.count('unknown'))
        self.assertEqual('empty', predictions[-1])

    def test_reject_invalid_coordinates_and_ids(self):
        for values in ([math.nan, 0], [0, math.inf]):
            with self.assertRaises(ValueError):
                assign([], values, ['empty']*361)
        with self.assertRaises(ValueError):
            aggregate([sample(-.2, 0)])
        with self.assertRaises(ValueError):
            aggregate([sample(0, math.nan)])
        with self.assertRaises(ValueError):
            assign([candidate(0, 2, 2), candidate(0, 3, 3)], [0, 0], ['empty']*361)


if __name__ == '__main__':
    unittest.main()
