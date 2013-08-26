#!/usr/bin/env python
import unittest
from jsoncert import *

class JsonCertTest(unittest.TestCase):

    def test(self):
        cert = JsonCert.getcert()
        msg = "sign me"
        signed_msg = cert.sign_object(msg)
        org_msg = cert.unsign_object(signed_msg)
        self.assertEqual(msg, org_msg)

        ser_obj = JsonCert.serialize(cert.as_dict)
        obj = JsonCert.deserialize(ser_obj)

        # need to change from unicode to string
        kvpairs = { 'key':str(obj['key']),'sig':str(obj['sig'])}
        new_cert = JsonCert(kvpairs)

        self.assertEqual(cert.pubkey, new_cert.pubkey)
        self.assertEqual(cert.as_dict['sig'], new_cert.as_dict['sig'])


if __name__ == '__main__':
    unittest.main()

