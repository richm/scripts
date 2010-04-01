
import os
import sys
import ldap
import ldif
import pprint
from dsadmin import DSAdmin, Entry

host = "localhost.localdomain"
port = 1100
binddn = "cn=directory manager"
bindpw = "password"
ldiffile = "/share/internal/tetframework/testcases/DS/6.0/import/airius10k.ldif"
basedn = "o=airius.com"

class ReadLdif(ldif.LDIFParser):
    def __init__(
        self,
        input_file,
        ignored_attr_types=None,max_entries=0,process_url_schemes=None
    ):
        """
        See LDIFParser.__init__()
        
        Additional Parameters:
        all_records
        List instance for storing parsed records
        """
        self.dndict = {} # maps dn to Entry
        self.cndict = {} # maps cn to Entry
        self.dnlist = [] # contains entries in order read
        self.input_file = input_file
        myfile = open(input_file, "r")
        ldif.LDIFParser.__init__(self,myfile,ignored_attr_types,max_entries,process_url_schemes)
        self.parse()
        myfile.close()

    def fixattr(self,ent,attr):
        val = ent.getValue(attr)
        if val:
            if val.startswith("cn="): return # already a DN
            othent = self.cndict.get(val, None)
            if not othent:
                # print "Error: could not find %s under %s" % (val, basedn)
                # just make something up - it's bogus anyway
                val = "cn=%s,ou=imaginary,%s" % (val, basedn)
            else:
                val = othent.dn
            ent.setValue(attr, val)

    def fixdnattrs(self,attrlist):
        for ent in self.dnlist:
            for attr in attrlist:
                self.fixattr(ent,attr)

    def printit(self):
        for ent in self.dnlist:
            sys.stdout.write(str(ent))

    def handle(self,dn,entry):
        """
        Append single record to dictionary of all records.
        """
        ent = Entry((dn, entry))
        normdn = DSAdmin.normalizeDN(dn)
        self.dndict[normdn] = ent
        cn = ent.cn
        if cn:
            self.cndict[cn] = ent
        self.dnlist.append(ent);

rdr = ReadLdif(ldiffile)
#rdr.fixdnattrs(['manager', 'secretary'])
rdr.printit()
