import unittest
from local_network import parse_config

class LocalNetworkTests(unittest.TestCase):
    def test_private_wifi(self):
        value = parse_config('{"ip":"172.16.0.205","prefix":24,"gateway":"172.16.0.1","interface":"Wi-Fi"}')
        self.assertEqual(value['subnet'], '172.16.0.0/24')
        self.assertEqual(value['gateway'], '172.16.0.1')
    def test_never_guess_large_subnet(self):
        self.assertIsNone(parse_config('{"ip":"10.10.0.20","prefix":16,"gateway":"10.10.0.1"}'))
    def test_reject_public(self):
        self.assertIsNone(parse_config('{"ip":"8.8.8.8","prefix":24,"gateway":"8.8.8.1"}'))
    def test_reject_missing_gateway(self):
        self.assertIsNone(parse_config('{"ip":"10.1.1.5","prefix":24,"gateway":"10.2.2.1"}'))
    def test_invalid_json(self):
        self.assertIsNone(parse_config('failure'))

if __name__ == '__main__': unittest.main()
