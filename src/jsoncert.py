#!/usr/bin/env python
import json, hashlib, base64, zlib, struct, pickle, os, unittest

from rsa import *

def int_to_b64(val):
  return base64.urlsafe_b64encode(ints_to_string(-1, val))

def b64_to_int(b64val):
  message = base64.urlsafe_b64decode(b64val)
  return list_to_int(256, (ord(c) for c in message))

class JsonCert(object):
  """Create a JSON-serializable certificate from a dict"""
  def __init__(self, content, pubkey=None, privkey=None):
    """If key=None, the key should be in content dict already, else overwrite"""
    self.as_dict = content
    self.privkey = privkey
    if pubkey:
      self.pubkey = pubkey
      self.as_dict['key'] = JsonCert.key_to_str(self.pubkey)
    elif 'key' in self.as_dict:
      self.pubkey = JsonCert.str_to_key(self.as_dict['key'])
    else:
      raise Exception("No public key in certificate")

    if 'sig' in self.as_dict:
      sig = self.as_dict['sig']
      del self.as_dict['sig']
      #verify:
      self.keyid = hashlib.sha384(JsonCert.serialize(self.as_dict)).digest() 
      compkid = rsa_cbc_d(self.pubkey, base64.urlsafe_b64decode(sig)) 
      if compkid != self.keyid:
        raise Exception('Invalid self-signature in keyid %s' % \
                        base64.urlsafe_b64encode(self.keyid))
      #things look good, put the signature back:
      self.as_dict['sig'] = sig
    else:
      if not privkey:
        raise Exception("Unsigned certificate without private key")
      else:
        self.keyid = hashlib.sha384(JsonCert.serialize(self.as_dict)).digest() 
        sigdata = rsa_cbc_e(self.privkey, self.keyid)
        self.as_dict['sig'] = base64.urlsafe_b64encode(sigdata)
    self.keyid64 = base64.urlsafe_b64encode(self.keyid)
      
  @staticmethod
  def generate(bits, kvpairs):
    if 'key' in kvpairs:
      raise Exception('key already present in certificate attributes')
    if 'sig' in kvpairs:
      raise Exception('sig already present in certificate attributes')
    rng = SecureRandom()
    (pub, priv) = genkeypair(rng, bits)
    return JsonCert(kvpairs, pub, priv)

  def sign_object(self, obj):
    if not self.privkey:
      raise Exception("Certificate has no private key, cannot sign")
    as_str = self.serialize(obj)
    return {'keyid' : self.keyid64,
            'signed': base64.urlsafe_b64encode(rsa_cbc_e(self.privkey, as_str)) }

  def unsign_object(self, obj):
    if self.keyid64 != obj['keyid']:
      raise Exception("Certificate keyid(%s) doesn't match signed data keyid(%s)" \
                      % (self.keyid64, obj['keyid']))
    signed = base64.urlsafe_b64decode(obj['signed'])
    unsigned = rsa_cbc_d(self.pubkey, signed)
    return self.deserialize(unsigned)
 
  @staticmethod
  def key_to_str(key):
    return "rsa:%s,%s" % (int_to_b64(key[0]),int_to_b64(key[1]))

  @staticmethod
  def str_to_key(str_key):
    if str_key[0:4] != "rsa:":
      raise Exception("Not an RSA key: %s" % str_key) 
    return tuple(b64_to_int(x) for x in str_key[4:].split(","))

  @staticmethod
  def serialize(obj):
    """use json + crc checksum at the end to catch errors"""
    data = json.dumps(obj, sort_keys=True, separators=(',',':')).encode("utf-8")
    return data + struct.pack(">i", zlib.crc32(data))

  @staticmethod
  def deserialize(str_ob):
    """use json + crc checksum at the end to catch errors"""
    crccomp = zlib.crc32(str_ob[:-4])
    crcval = struct.unpack(">i", str_ob[-4:])[0] 
    if crcval != crccomp:
      raise Exception("CRC mismatch: computed(%i) != stored(%i)" % (crccomp, crcval))
    return json.loads(str_ob[:-4].decode("utf-8"))

  @staticmethod
  def getcert():
    if os.path.exists('key.data'):
      key = pickle.load(open("key.data","r"))
      cert = JsonCert({}, key['pub'],key['priv'])
    else:
      cert = JsonCert.generate(1024,None)
      key = { 'pub':cert.pubkey, 'priv':cert.privkey}
      pickle.dump(key, open('key.data', 'w+'))

    return cert


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

