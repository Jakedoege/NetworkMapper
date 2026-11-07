import unittest
from identity import determine_identity, mac_hint, meaningful_web, smart_positions

class IdentityTests(unittest.TestCase):
    def test_proxmox_mac(self):
        self.assertEqual(mac_hint('bc:24:11:12:34:56')[0], 'Proxmox virtual NIC')
    def test_generic_web_suppressed(self):
        self.assertEqual(meaningful_web('401 Unauthorized'), '')
        self.assertEqual(meaningful_web('Moved Temporarily'), '')
        self.assertEqual(meaningful_web('CellRx Parts & Repair'), 'CellRx Parts & Repair')
    def test_gateway(self):
        d = determine_identity('172.16.0.1', {}, '172.16.0.1')
        self.assertEqual((d['suggested_type'], d['confidence']), ('Router', 'High'))
    def test_proxmox_service(self):
        self.assertEqual(determine_identity('172.16.0.50', {'ports':[8006]}, '')['suggested_type'], 'Server')
    def test_ambiguous_ssh(self):
        self.assertEqual(determine_identity('172.16.0.3', {'ports':[22]}, '')['confidence'], 'Low')
    def test_layout(self):
        d = {'172.16.0.1':{'type':'Router'}, '172.16.0.50':{'type':'Server'}, '172.16.0.25':{'type':'PC'}}
        pos = smart_positions(d, '172.16.0.1')
        self.assertEqual(set(pos), set(d))
        self.assertLess(pos['172.16.0.1'][1],pos['172.16.0.50'][1])

if __name__=='__main__':
    unittest.main()
