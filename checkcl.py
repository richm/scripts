#!/usr/bin/env python

import sys
import string
import ldif
import re
from bisect import insort

# we want to find out if
# * all csns in one server are in the other servers
# ** no missing csns, no extra csns
# * no duplicate csns in a single server
# * csns are "in order"
# ** assumes there is some way to determine
#    what order the entries were added in, such
#    as cn=1, cn=2, etc.

class CSN:
  USE_RID = True
  def __init__(self,csnstr):
    self.ts = int(csnstr[:8], 16)
    self.seq = int(csnstr[8:12], 16)
    self.rid = int(csnstr[12:16])
  def __str__(self):
    return "%08x%04x%04x0000" % (self.ts, self.seq, self.rid)
  __repr__ = __str__
  def __cmp__(self, oth):
    ret = self.ts - oth.ts
    if not ret:
      ret = self.seq - oth.seq
      if not ret and CSN.USE_RID:
        ret = self.rid - oth.rid
    return ret
  def __lt__(self, oth): return self.__cmp__(oth) < 0
  def __le__(self, oth): return self.__cmp__(oth) <= 0
  def __gt__(self, oth): return self.__cmp__(oth) > 0
  def __ge__(self, oth): return self.__cmp__(oth) >= 0
  def __eq__(self, oth): return self.__cmp__(oth) == 0
  def __ne__(self, oth): return self.__cmp__(oth) != 0
  def __hash__(self): # use a CSN as a hash key
    if CSN.USE_RID:
      return (self.ts << 32) | (self.seq << 16) | self.rid
    else:
      return (self.ts << 16) | self.seq

# Can't use ldif.LDIFParser.parse - the cl.ldif
# files are not well-formed - have to use copypasta
class CLDB(ldif.LDIFParser):
  cnpat = re.compile(r'cn=([\d]+),')

  def __init__(self,input_file):
    myfile = open(input_file, "r")
    self.csns = {} # key is csn string, value is (dn, changetype, CSN()) tuple
    self.byrid = {} # key is rid - value is hash
    # key is changetype - value is tuple (cn, CSN())
    ldif.LDIFParser.__init__(self,myfile)
    self.parse()
    myfile.close()
    self.name = input_file
    # create the list of 

  def parse(self):
    """
    Continously read and parse LDIF records
    """
    self._line = self._input_file.readline()

    while self._line and \
          (not self._max_entries or self.records_read<self._max_entries):

      # Reset record
      version = None; dn = None; changetype = None; modop = None; entry = {}

      if self._line == '-\n': # will return None,None
        attr_type,attr_value = self._parseAttrTypeandValue()
      attr_type,attr_value = self._parseAttrTypeandValue()

      while attr_type!=None and attr_value!=None:
        if attr_type=='dn':
          # attr type and value pair was DN of LDIF record
          if dn!=None:
            raise ValueError, 'Two lines starting with dn: in one record.'
          if not ldif.is_dn(attr_value):
            raise ValueError, 'No valid string-representation of distinguished name %s.' % (repr(attr_value))
          dn = attr_value
        elif attr_type=='version' and dn is None:
          version = 1
        elif attr_type=='changetype':
          # attr type and value pair was DN of LDIF record
          if changetype!=None:
            raise ValueError, 'Two lines starting with changetype: in one record.'
          if not ldif.valid_changetype_dict.has_key(attr_value):
            raise ValueError, 'changetype value %s is invalid.' % (repr(attr_value))
          # Add the attribute to the entry if not ignored attribute
          if entry.has_key(attr_type):
            entry[attr_type].append(attr_value)
          else:
            entry[attr_type]=[attr_value]
        elif attr_value!=None and \
             not self._ignored_attr_types.has_key(string.lower(attr_type)):
          # Add the attribute to the entry if not ignored attribute
          if entry.has_key(attr_type):
            entry[attr_type].append(attr_value)
          else:
            entry[attr_type]=[attr_value]

        # Read the next line within an entry
        if self._line == '-\n': # will return None,None
          attr_type,attr_value = self._parseAttrTypeandValue()
        attr_type,attr_value = self._parseAttrTypeandValue()

      if entry:
        # append entry to result list
        self.handle(dn,entry)
        self.records_read = self.records_read+1

    return # parse()

  # parse() calls handle for each entry read
  def handle(self,dn,entry):
    """
    Append single record to dictionary of all records.
    """
    changetype = None
    if entry.has_key('changetype'):
      changetype = entry['changetype'][0]
    cnval = -1
    if dn and CLDB.cnpat.match(dn):
      cnval = int(CLDB.cnpat.match(dn).group(1))
#    print "CLDB.handle: dn", dn, " changetype", changetype, " cn", cnval
    if entry.has_key('csn'):      
      csnstr = entry['csn'][0]
      csn = CSN(csnstr)
      tup = (dn, changetype, csn)
      if self.csns.has_key(csn):
        print "Error: entry %s has dup csn %s" % (dn, csnstr)
        print "existing records:", self.csns[csn]
        self.csns[csn].append(tup)
      else:
        self.csns[csn] = [tup]
      if not self.byrid.has_key(csn.rid):
        self.byrid[csn.rid] = {changetype: {'ary': [], 'hash': {}}}
      if not self.byrid[csn.rid].has_key(changetype):
        self.byrid[csn.rid][changetype] = {'ary': [], 'hash': {}}
      insort(self.byrid[csn.rid][changetype]['ary'], cnval)
      self.byrid[csn.rid][changetype]['hash'][cnval] = csn
    else:
      print "entry", dn, " has no csn"

  def findOutOfOrder(self):
    for (rid, byctype) in self.byrid.iteritems():
      for (ctype, ahhash) in byctype.iteritems():
        lastcsn = None
        for cn in ahhash['ary']:
          csn = ahhash['hash'][cn]
#          print "rid=", rid, " ctype-", ctype, "cn=", cn, "csn =", csn
          CSN.USE_RID = False # ignore rid for comparison
          if lastcsn and csn < lastcsn:
            print "Error: csn", csn, " for cn", cn, " is out of order"
          lastcsn = csn
          CSN.USE_RID = True # reset

  def checkCSNs(self,oth,verbose=False):
    # see if there are any csns in self that are not present
    # in oth
    # see if there are any csns in oth that are not present
    # in self
    ii = 0
    nmissing = 0
    mincsn = None
    maxcsn = None
    for csn in self.csns.iterkeys():
      ii = ii + 1
      if not oth.csns.has_key(csn):
        nmissing = nmissing + 1
        if verbose: print "Error:", oth.name, "is missing CSN", csn
        if not mincsn:
          mincsn = csn
        if not maxcsn:
          maxcsn = csn
        if csn < mincsn:
          mincsn = csn
        if csn > maxcsn:
          maxcsn = csn
    print "Changelog", self.name, "has", ii, " csns"
    if nmissing > 0:
      print "Server", oth.name, "is missing", nmissing, "csns - min", mincsn, "max", maxcsn
    ii = 0
    nmissing = 0
    mincsn = None
    maxcsn = None
    for csn in oth.csns.iterkeys():
      ii = ii + 1
      if not self.csns.has_key(csn):
        nmissing = nmissing + 1
        if verbose: print "Error:", self.name, "is missing CSN", csn
        if not mincsn:
          mincsn = csn
        if not maxcsn:
          maxcsn = csn
        if csn < mincsn:
          mincsn = csn
        if csn > maxcsn:
          maxcsn = csn
    print "Changelog", oth.name, "has", ii, " csns"
    if nmissing > 0:
      print "Server", self.name, "is missing", nmissing, "csns - min", mincsn, "max", maxcsn

print "Reading in %d changelog LDIF files . . ." % len(sys.argv[1:])
cldbs = []
for f in sys.argv[1:]:
    cldb = CLDB(f)
    cldbs.append(cldb)
    print "Read in changelog", cldb.name
    cldb.findOutOfOrder()
    for oth in cldbs[:-1]:
      cldb.checkCSNs(oth)
