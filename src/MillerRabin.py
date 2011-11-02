#!/usr/bin/env python

# Copyright (c) 2011 the authors listed at the following URL, and/or
# the authors of referenced articles or incorporated external code:
# http://en.literateprograms.org/Miller-Rabin_primality_test_(Python)?action=history&offset=20101013093632
# 
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
# 
# Retrieved from: http://en.literateprograms.org/Miller-Rabin_primality_test_(Python)?oldid=16957

import sys, rsa

def miller_rabin_pass(a, s, d, n):
    #a_to_power = pow(a, d, n)
    a_to_power = rsa.expmod(a, d, n)
    if a_to_power == 1:
        return True
    for i in xrange(s-1):
        if a_to_power == n - 1:
            return True
        a_to_power = (a_to_power * a_to_power) % n
    return a_to_power == n - 1


def miller_rabin(n, rand_func):
    d = n - 1
    s = 0
    while d % 2 == 0:
         d >>= 1
         s += 1

    k = 64	
    #this gives probability 2^{-2k} probability of error
    for repeat in xrange(k):
        a = 0
        while a == 0:
            a = rand_func(n)
        if not miller_rabin_pass(a, s, d, n):
            return False
    return True

def gen_prime(nbits, rand):
    while True:
        p = rand.get_int_bits(nbits)
        p |= 2**nbits | 1
        if miller_rabin(p, rand.randint):
          return p

if __name__ == "__main__":
    rand = rsa.SecureRandom(open("/dev/urandom"))
    if sys.argv[1] == "test":
        n = long(sys.argv[2])
        print (miller_rabin(n, rand.randint) and "PRIME" or "COMPOSITE")
    elif sys.argv[1] == "genprime":
        nbits = int(sys.argv[2])
        print gen_prime(nbits, rand)
