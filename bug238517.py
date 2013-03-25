from bug_harness import DSAdminHarness as DSAdmin
from dsadmin import Entry


import os
import sys
import time
import ldap
import ldif

host1 = "localhost.localdomain"
host2 = host1
cfgport = 1100
port1 = cfgport+30
port2 = cfgport+40

#os.environ['USE_DBX'] = "1"
m1replargs = {
	'suffix': "dc=example,dc=com",
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl",
    'chain' : True
}

m1 = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': 'dc=example,dc=com',
	'verbose': True,
    'no_admin': True
})
#del os.environ['USE_DBX']

print "Set the cache size really low"
replace = [(ldap.MOD_REPLACE, 'nsslapd-cachememsize', '500000')]
m1.modify_s('cn=userRoot,cn=ldbm database,cn=plugins,cn=config', replace)

print "restart the server to force cache size change to take effect"
m1.stop(True)
m1.start(True)
time.sleep(1)

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (m1.sroot,m1.inst)
else:
    initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')

class CacheStats:
    def __init__(
        self,
        dsadmin,
        dbname
    ):
        """
        Keep track of cache statistics
        """
        self.dsadmin = dsadmin
        self.dbname = dbname
        self.monitordn = "cn=monitor,cn=%s,cn=ldbm database,cn=plugins,cn=config" % dbname
        self.beginsize = 0
        self.begincount = 0
        self.currentsize = 0
        self.currentcount = 0
        self.minsize = 9999999999
        self.maxsize = 0
        # attributes we pull from monitor entry
        self.monitorattrs = ['currententrycachecount', 'currententrycachesize', 'entrycachehitratio',
                             'entrycachehits', 'entrycachetries', 'maxentrycachesize']

    def mark(self):
        ent = self.dsadmin.getEntry(self.monitordn, ldap.SCOPE_BASE,
                                    "objectclass=*", self.monitorattrs)
        prevsize = self.currentsize
        prevcount = self.currentcount
        self.currentsize = int(ent.currententrycachesize)
        if not self.beginsize:
            self.beginsize = self.currentsize
        self.currentcount = int(ent.currententrycachecount)
        if not self.begincount:
            self.begincount = self.currentcount
        # delta is size of one entry
        if prevcount < self.currentcount:
            delta = self.currentsize - prevsize
            if delta > 0 and delta < self.minsize:
                self.minsize = delta
            if delta > self.maxsize:
                self.maxsize = delta

    def report(self):
        return """
        Begin count: %d
        Begin size: %d
        Current count: %d
        Current size: %d
        Avg size: %d
        Min size: %d
        Max size: %d
        """ % (self.begincount, self.beginsize, self.currentcount, self.currentsize,
               (self.currentsize / self.currentcount), self.minsize, self.maxsize)

class LDIFAdd(ldif.LDIFParser):
    def __init__(
        self,
        input_file,
        dsadmin,
        cachestats,
        ignored_attr_types=None,max_entries=0,process_url_schemes=None
    ):
        """
        See LDIFParser.__init__()
        
        Additional Parameters:
        all_records
        List instance for storing parsed records
        """
        self.dsadmin = dsadmin
        self.cs = cachestats
        myfile = input_file
        if isinstance(input_file,str) or isinstance(input_file,unicode):
            myfile = open(input_file, "r")
        ldif.LDIFParser.__init__(self,myfile,ignored_attr_types,max_entries,process_url_schemes)
        self.parse()
        if isinstance(input_file,str) or isinstance(input_file,unicode):
            myfile.close()

    def handle(self,dn,entry):
        """
        Append single record to dictionary of all records.
        """
        if not dn:
            dn = ''
        newentry = Entry((dn, entry))
        try:
            self.dsadmin.add_s(newentry)
        except ldap.ALREADY_EXISTS:
            print "Entry %s already exists - skipping" % dn
            return
        cs.mark()

cs = CacheStats(m1, 'userRoot')
cs.mark()
print "Initial cache stats are", cs.report()

la = LDIFAdd(initfile, m1, cs)

print "Final cache stats are", cs.report()

m1.importLDIF(initfile, '', "userRoot", True)

cs = CacheStats(m1, 'userRoot')
cs.mark()
print "Initial cache stats are", cs.report()
print "search every entry to populate cache"
ents = m1.search_s("dc=example,dc=com", ldap.SCOPE_SUBTREE, "objectclass=*")
ii = 0
for ent in ents:
    cs.mark()
    ii = ii + 1
print "Found %d entries" % ii

print "Final cache stats are", cs.report()
