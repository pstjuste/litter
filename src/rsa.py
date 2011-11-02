#!/usr/bin/env python

def list_to_int(base, l):
  """consider the string as a MSB-first binary number
     return that number in base as a list"""
  return reduce(lambda x,y: base * x + y, l)

def int_to_list(base, val):
  """inverse of list_to_int"""
  ints = []
  while val > 0:
    val,m = divmod(val, base)
    ints.append(m)
  ints.reverse() 
  return ints

class SecureRandom(object):
  #pass in a file or a stream that has truly random data
  def __init__(self, random_file=None):
    if not random_file:
      random_file = open('/dev/urandom')
    self.fileobj = random_file

  def get_int_bits(self, bits):
    #convert to a normal integer:
    byte_cnt, rem = divmod(bits, 8)
    if rem:
      byte_cnt += 1
    return list_to_int(256, (ord(c) for c in self.fileobj.read(byte_cnt))) 

  def randint(self, strict_ub):
    bits = 0
    temp = strict_ub
    while temp > 0:
      temp >>= 8
      bits += 8
    r = strict_ub
    while r >= strict_ub:
      r = self.get_int_bits(bits)
    return r

def is_prime(x):
  """very slow algorithm (exponential), but clear,
     there are polynomial time algorithms for this,
     but more complex"""
  if x < 2:
    return False
  y = 2 
  while y*y <= x:
    if x % y == 0:
      return False
    y = y + 1
  #if we get here, it's definitely prime
  return True

def extended_gcd(a, b):
    '''solve ax + by = gcd(a,b), return x,y,gcd(a,b)'''
    x = 0; lastx = 1
    y = 1; lasty = 0
    while b != 0:
        q, m = divmod(a, b)
        a, b = b, m
        x, lastx = lastx - q*x, x
        y, lasty = lasty - q*y, y        
    return (lastx, lasty, a)

def gcd(a,b):
  if a < b:
    return gcd(b,a)
  else:
    if b == 0:
      return a
    else:
      return gcd(b, a % b)

def generate_prime(rng, bits):
  import MillerRabin
  return MillerRabin.gen_prime(bits, rng)
  #prime_cand = rng.get_int_bits(bits) 
  #while not is_prime(prime_cand):
  #  prime_cand = rng.get_int_bits(bits) 
  #return prime_cand

def mult_inv(e, x):
  """solve d*e + b*x = 1 which is d*e = 1 mod x if gcd(e,x) == 1"""
  (b, d, gcd) = extended_gcd(x,e)
  if gcd != 1:
    raise Exception("%i has no inverse mod %i" % (e,x))
  while d < 0:
    d = d + x
  assert (e*d % x == 1)
  return d

def genkeypair(rng, bits):
  p, q = generate_prime(rng, bits/2), generate_prime(rng, bits/2)
  while p == q:
    q = generate_prime(rng, bits/2)
  n = p*q #should be about bits long
  phi = (p-1)*(q-1)
  #make an e co-prime to phi
  e = rng.get_int_bits(bits)
  while (e > phi) or (gcd(e,phi) != 1):
    e = rng.get_int_bits(bits)
  d = mult_inv(e, phi)
  public_key = (e,n)
  private_key = (d,n)
  return (public_key, private_key)

def expmod(v, expo, modu):
  """compute modular exponent using
     the binary expansion algo"""
  result = 1
  power = v
  while expo:
    if (expo & 1): #use this power:
      result = (result * power) % modu
    expo = expo >> 1
    power = (power * power) % modu
  return result

def rsa(key, message):
  #todo implement blinding
  expo, modu = key
  #same as: return (message ** expo) % modu
  return expmod(message, expo, modu) 

def rsa_cbc_e(key, mess_string):
  (exponent, modulus) = key
  plain = string_to_ints(modulus, mess_string, True) 
  cipher = []
  c_prev = 0
  for p in plain:
    p = (p + c_prev) % modulus
    c = rsa(key, p) #c = e(k,p+c_p) => d(k,c) - c_p = p
    cipher.append(c)
    c_prev = c
  return ints_to_string(modulus, cipher) 

def rsa_cbc_d(key, ciph_string):
  (exponent, modulus) = key
  cipher = string_to_ints(modulus, ciph_string) 
  c_prev = 0
  plain = []
  for c in cipher:
    p = (rsa(key, c) - c_prev) % modulus
    c_prev = c
    plain.append(p)
  return ints_to_string(modulus, plain, True) 

def string_to_ints(base, message, pad = False):
  """consider the string as a MSB-first binary number
     return that number in base as a list"""
  #a zero in the first byte, would be dropped, so, we escape it:
  # 00 -> 02 00, 01 -> 02 01, 02 -> 02 02 (this prevents 00, 01 messages)
  join_str = set( (chr(0), chr(1), chr(2)) )
  if pad and (message[0] in join_str):
    #prefix with 02
    message = chr(2) + message
  val256 = list_to_int(256, (ord(c) for c in message))
  return int_to_list(base, val256)

def ints_to_string(base, ints, chop = False):
  """use -1 base to handle the case of a raw int"""
  if base == -1:
    base = 256
    ints = int_to_list(256, ints)
  if base != 256:
    num = list_to_int(base, ints)
    ints = int_to_list(256, num)
  if chop and (ints[0] == 2):
    #chop off the 02 prefix
    ints = ints[1:]
  return "".join( (chr(x) for x in ints))

def gen_main(argv):
  pub, priv = genkeypair(rng, int(argv[2]))
  key = {"pub" : pub, "priv" : priv }
  pickle.dump(key, open("key.data","w+"))

def enc_main(argv):
  key = pickle.load(open("key.data","r"))
  pub, priv = key["pub"], key["priv"]
  print "public key: %s\nprivate key: %s\n" % (pub, priv)
  plain = argv[2]
  print "message (%i): %s\n" % (len(plain),plain)
  ciph = rsa_cbc_e(pub, plain)
  print "encrypted (%i): %s\n" % (len(ciph), [ hex(ord(s)) for s in ciph ])
  decrypted = rsa_cbc_d(priv, ciph)
  print "decrypted (%i): %s\n" % (len(decrypted),decrypted)

def assert_rt(key, message):
  pub, priv = key["pub"], key["priv"]
  ciph = rsa_cbc_e(pub, message)
  dec = rsa_cbc_d(priv, ciph)
  try:
    assert message == dec
    return 1
  except:
    print len(message), len(dec)
    print "mes: %s" % [ ord(x) for x in message ]
    print "dec: %s " % [ ord(x) for x in dec ]
    return 0

def test_main(argv):
  key = pickle.load(open("key.data","r"))
  import random
  good = 0
  total = 100
  for i in xrange(total):
    length = random.randint(1, 10000)
    message = "".join( chr(random.randint(0,255)) for j in xrange(length)) 
    good += assert_rt(key, message)
  #test special prefixes:
  spec = [ assert_rt(key, m) for m in [ "".join( (chr(0), chr(0)) ),
              "".join( (chr(1), chr(0)) ),
              "".join( (chr(2), chr(0)) ),
              "".join( (chr(0),) ),
              "".join( (chr(1),) ),
              "".join( (chr(2),) ) ] ]
  good += sum(spec)
  total += len(spec)
  print "Passed: %s/%s" % (good, total)

if __name__ == "__main__":
  rng = SecureRandom(open("/dev/urandom"))
  import sys
  import pickle
  meths = { 'gen' : gen_main,
            'enc' : enc_main,
            'test' : test_main }
  meths[sys.argv[1]](sys.argv)
