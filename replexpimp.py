
import os
import sys
import time
import ldap
import ldif
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
port1 = 1200
basedn = "dc=example,dc=com"

srv = DSAdmin.createInstance({
    'newrootpw': 'password',
    'newhost': host1,
    'newport': port1,
    'newinst': 'srv',
    'newsuffix': basedn,
    'verbose': False,
    'no_admin': True
})

basedns = [basedn]
benames = ['userRoot']
base1 = "ou=people," + basedn
basedns.append(base1)
srv.addSuffix(base1)
ents = srv.getBackendsForSuffix(base1, ['cn'])
benames.append(ents[0].cn)
base2 = "ou=people1," + basedn
basedns.append(base2)
srv.addSuffix(base2)
ents = srv.getBackendsForSuffix(base2, ['cn'])
benames.append(ents[0].cn)

fixfile = "%s/100k.ldif" % os.environ.get('PREFIX', '/usr')
initfiles = [fixfile.replace("100k", bename) for bename in benames]

class AddEntriesForSuffix(ldif.LDIFParser):
    def __init__(
        self,
        input_file,output_files,basedns,
        ignored_attr_types=None,max_entries=0,process_url_schemes=None,
        base64_attrs=None,cols=76,line_sep='\n'
    ):
        """
        See LDIFParser.__init__()
        
        Additional Parameters:
        all_records
        List instance for storing parsed records
        """
        myfile = input_file
        if isinstance(input_file,basestring):
            myfile = open(input_file, "r")
        ldif.LDIFParser.__init__(self,myfile,ignored_attr_types,max_entries,process_url_schemes)

        self.outfiles = []
        self.outldifs = []
        for output_file in output_files:
            if isinstance(output_file,basestring):
                outfile = open(output_file, "w")
            self.outfiles.append(outfile)
            self.outldifs.append(ldif.LDIFWriter(outfile,base64_attrs,cols,line_sep))
        self.basedns = basedns
        self.iterlist = zip(self.basedns, self.outldifs)
        self.iterlist.reverse()
        
        self.parse()
        if isinstance(input_file,basestring):
            myfile.close()

        for (fn, fd) in zip(output_files, self.outfiles):
            if isinstance(fn,basestring):
                fd.close()

    def handle(self,dn,entry):
        """
        assumes basedns[0] is the parent, basedns[1] already exists,
        and we want to create entries for basedns[2]
        """
        normdn = DSAdmin.normalizeDN(dn)
        for (basedn, ld) in self.iterlist:
            if normdn.endswith(basedn):
                ld.unparse(dn,entry)
                if basedn == self.basedns[1]:
                    dn = normdn.replace(basedn,self.basedns[2])
                    for (attr, vals) in entry.iteritems():
                        for ii in xrange(0, len(vals)):
                            vals[ii] = vals[ii].replace(basedn,self.basedns[2])
                    self.outldifs[2].unparse(dn,entry)
                break

neednewfile = False
if neednewfile:
    aefs = AddEntriesForSuffix(fixfile, initfiles, basedns)

for (fn, bename) in zip(initfiles, benames):
    srv.importLDIF(fn, '', bename, True)

print "change the cache size to the minimum"
mod = [(ldap.MOD_REPLACE, "nsslapd-cachememsize", "512000"),
       (ldap.MOD_REPLACE, "nsslapd-dncachememsize", "512000")]
ents = srv.getBackendsForSuffix(base1)
for ent in ents:
    srv.modify_s(ent.dn, mod)
ents = srv.getBackendsForSuffix(base2)
for ent in ents:
    srv.modify_s(ent.dn, mod)
srv.stop(True)
#os.environ["USE_GDB"] = "1"
srv.start(True)

msgid1 = srv.search(basedn, ldap.SCOPE_SUBTREE, "objectclass=*")

taskdns = []
for (bename, fn) in zip(benames, initfiles):
    outfile = fn + ".out"
    cn = "export" + str(int(time.time())) + "-" + bename
    taskdn = "cn=%s,cn=export,cn=tasks,cn=config" % cn
    entry = Entry(taskdn)
    entry.setValues('objectclass', 'top', 'extensibleObject')
    entry.setValues('cn', cn)
    entry.setValues('nsFilename', outfile)
    entry.setValues('nsInstance', bename)
    srv.add_s(entry)
    taskdns.append(taskdn)

msgid2 = srv.search(basedn, ldap.SCOPE_SUBTREE, "objectclass=*")

attrlist = ['nsTaskLog', 'nsTaskStatus', 'nsTaskExitCode', 'nsTaskCurrentItem', 'nsTaskTotalItems']
for taskdn in taskdns:
    try:
        entry = srv.getEntry(taskdn, ldap.SCOPE_BASE, "(objectclass=*)", attrlist)
        print entry
    except ldap.NO_SUCH_OBJECT:
        print "no task for", taskdn

done = False
nents1 = 0
type1 = 0
nents2 = 0
type2 = 0
while not done:
    if type1 != ldap.RES_SEARCH_RESULT:
        type1, ent1 = srv.result(msgid1, 0)
        nents1 += 1
    if type2 != ldap.RES_SEARCH_RESULT:
        type2, ent2 = srv.result(msgid2, 0)
        nents2 += 1
    done = (type1 == ldap.RES_SEARCH_RESULT) and (type2 == ldap.RES_SEARCH_RESULT)

for taskdn in taskdns:
    try:
        entry = srv.getEntry(taskdn, ldap.SCOPE_BASE, "(objectclass=*)", attrlist)
        print entry
    except ldap.NO_SUCH_OBJECT:
        print "no task for", taskdn

print "done with searches, found", nents1, "and", nents2
print "start adding entries"
for ii in xrange(1,101):
    cn = "user%d" % ii
    dn = "cn=%s,%s" % (cn, base1)
    entry = Entry(dn)
    entry.setValues('objectclass', 'top', 'person')
    entry.setValues('sn', 'testuser')
    try: srv.add_s(entry)
    except ldap.ALREADY_EXISTS: print dn, "already exists"
    if ii % 3:
        print "try to add a bogus entry"
        dn = "cn=%s,,,,%s" % (cn, base1)
        entry = Entry(dn)
        entry.setValues('objectclass', 'top', 'person')
        entry.setValues('sn', 'testuser')
        try: srv.add_s(entry)
        except ldap.LDAPError, e: print "adding", dn, "threw error", e
    dn = "cn=%s,%s" % (cn, base2)
    entry = Entry(dn)
    entry.setValues('objectclass', 'top', 'person')
    entry.setValues('sn', 'testuser')
    try: srv.add_s(entry)
    except ldap.ALREADY_EXISTS: print dn, "already exists"
    if ii % 3:
        print "try to add a bogus entry"
        dn = "cn=%s,,,,%s" % (cn, base2)
        entry = Entry(dn)
        entry.setValues('objectclass', 'top', 'person')
        entry.setValues('sn', 'testuser')
        try: srv.add_s(entry)
        except ldap.LDAPError, e: print "adding", dn, "threw error", e

for taskdn in taskdns:
    try:
        entry = srv.getEntry(taskdn, ldap.SCOPE_BASE, "(objectclass=*)", attrlist)
        print entry
    except ldap.NO_SUCH_OBJECT:
        print "no task for", taskdn
