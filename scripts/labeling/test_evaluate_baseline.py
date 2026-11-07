import unittest

from evaluate_baseline import parse_baseline


class BaselineTest(unittest.TestCase):
    def lines(self):
        return [f'B\t{c}\t{r}\tEMPTY' for r in range(19) for c in range(19)]

    def test_orders_coordinates_without_replacing_unknown(self):
        lines = self.lines()
        lines[0] = 'B\t0\t0\tBLACK'
        lines[-1] = 'B\t18\t18\tUNKNOWN'
        values = parse_baseline('\n'.join(reversed(lines)))
        self.assertEqual(['black']+['empty']*359+['unknown'], values)

    def test_rejects_incomplete_duplicate_out_of_bounds_and_invalid_state(self):
        lines = self.lines()
        for raw in (lines[:-1], lines+[lines[0]], lines[:-1]+['B\t19\t18\tEMPTY'],
                    lines[:-1]+['B\t18\t-1\tEMPTY'], lines[:-1]+['B\t18\t18\tUNCLASSIFIED'],
                    lines+['D\t0\t0\tBLACK\t1']):
            with self.subTest(tail=raw[-1]), self.assertRaises(ValueError):
                parse_baseline('\n'.join(raw))
