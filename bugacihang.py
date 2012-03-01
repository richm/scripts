import os
import sys
import time
import shutil
import ldap
from dsadmin import DSAdmin, Entry, LEAF_TYPE
from ldap.controls import SimplePagedResultsControl

print "start"
host1 = "localhost.localdomain"
port1 = 1389
basedn = "dc=example,dc=com"
dom = 'example.com'
dnsdom = 'localdomain'

#os.environ['USE_VALGRIND'] = '1'
ds = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'ds',
	'newsuffix': basedn,
	'no_admin': True
})

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (ds.sroot,ds.inst)
else:
    initfilesrc = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')
    initfile = "%s/var/lib/dirsrv/slapd-%s/ldif/Example.ldif" % (os.environ.get('PREFIX', ''), 'ds')
    shutil.copy(initfilesrc, initfile)
print "importing database"
ds.importLDIF(initfile, '', "userRoot", False)

dn2aci = (
    (basedn,[
        '(targetattr ="*")(version 3.0;acl "Directory Administrators Group";allow (all) (groupdn = "ldap:///cn=Directory Administrators, %s");)' % basedn,
        '(targetattr="*")(version 3.0; acl "Configuration Administrators Group"; allow (all) groupdn="ldap:///cn=Configuration Administrators,ou=Groups,ou=TopologyManagement,o=NetscapeRoot";)',
        '(targetattr="*")(version 3.0; acl "Configuration Administrator"; allow (all) userdn="ldap:///uid=admin,ou=Administrators,ou=TopologyManagement,o=NetscapeRoot";)',
        '(targetattr = "*")(version 3.0; acl "SIE Group"; allow (all) groupdn = "ldap:///cn=slapd-%s,cn=389 Directory Server,cn=Server Group,cn=%s,ou=%s,o=NetscapeRoot";)' % ('ds', host1, dom),
        '(targetattr = "physicalDeliveryOfficeName || homePhone || preferredDeliveryMethod || jpegPhoto || nsAIMid || mozillaHomeCountryName || audio || internationaliSDNNumber || postalAddress || roomNumber || mozillaWorkStreet2 || givenName || mozillaSecondEmail || userPKCS12 || userPassword || teletexTerminalIdentifier || mobile || manager || objectClass || userSMIMECertificate || mozillaHomeStreet || destinationIndicator || telexNumber || employeeNumber || secretary || uid || userCertificate || st || mozillaCustom4 || mozillaCustom3 || mozillaCustom2 || mozillaCustom1 || description || mozillaHomePostalCode || mail || labeledUri || businessCategory || x500UniqueIdentifier || ou || seeAlso || photo || mozillaNickname || mozillaHomeLocalityName || shadowLastChange || title || street || departmentNumber || mozillaHomeStreet2 || mozillaUseHtmlMail || mozillaHomeState || o || cn || l || initials || telephoneNumber || mozillaHomeUrl || x121Address") (version 3.0; acl "Authenticated user self access"; allow (read,compare,search,write)(userdn = "ldap:///self");)']),
    ('ou=groups,' + basedn,[
        '(targetattr != "userPKCS12 || userPassword") (target = "ldap:///ou=Groups, %s") (version 3.0;acl "Anonymous access within domain";allow (read,compare,search)(userdn = "ldap:///anyone");)' % basedn,
        '(targetattr != "userPKCS12 || userPassword") (target = "ldap:///ou=Groups, %s") (version 3.0; acl "SSSD access for mobile workstations";allow (read,compare,search) (userdn = "ldap:///uid=sssd, ou=Special Users, %s");)' % (basedn, basedn)]),
    ('ou=people,' + basedn,[
        '(targetattr != "userPKCS12 || userPassword") (target = "ldap:///ou=People, %s") (version 3.0;acl "Anonymous access within domain";allow (read,compare,search)(userdn = "ldap:///anyone");)' % basedn,
        '(targetattr != "userPKCS12 || userPassword") (target = "ldap:///ou=People, %s") (version 3.0; acl "SSSD access for mobile workstations";allow (read,compare,search) (userdn = "ldap:///uid=sssd, ou=Special Users, %s");)' % (basedn, basedn)]),
    ('ou=Special Users,' + basedn,[
        '(targetattr != "userPKCS12 || userPassword") (target = "ldap:///ou=Special Users,%s") (version 3.0;acl "Anonymous access within domain";allow (read,compare,search)(userdn = "ldap:///anyone");)' % basedn]),
    ('ou=eGW,' + basedn,[
        '(targetattr = "*") (target = "ldap:///ou=*,ou=eGW,%s") (version 3.0;acl "eGW Admin access";allow (read,compare,search,write,delete,add)(userdn = "ldap:///uid=egw,ou=Special Users,%s");)' % (basedn, basedn),
        '(targetattr = "homePhone || mobile || objectClass || mozillaCustom4 || mozillaCustom3 || mozillaCustom2 || mozillaCustom1 || mail || cn || telephoneNumber || facsimileTelephoneNumber") (target = "ldap:///ou=eGW,%s") (version 3.0;acl "Asterisk FAX Gateway/eGW phone and email list access";allow (read,compare,search)(userdn = "ldap:///uid=asterisk,ou=Special Users,%s");)' % (basedn, basedn)]),
    ('ou=accounts,ou=%s,ou=eGW,%s' % (dom, basedn),[
        '(targetattr != "userPKCS12 || userPassword") (target = "ldap:///ou=accounts,($dn),ou=eGW,%s") (version 3.0;acl "eGW account list access";allow (read,compare,search) (userdn = "ldap:///uid=*,ou=accounts,($dn),ou=eGW,%s");)' % (basedn, basedn),
        '(targetattr = "objectClass || uid") (target = "ldap:///ou=accounts,ou=%s,ou=eGW,%s") (version 3.0; acl "Apache/eGW account list access"; allow (read,compare,search) (userdn = "ldap:///uid=apache, ou=Special Users,%s");)' % (dom, basedn, basedn),
        '(targetattr = "homePhone || mobile || objectClass || mozillaCustom4 || mozillaCustom3 || mozillaCustom2 || mozillaCustom1 || mail || cn || telephoneNumber || facsimileTelephoneNumber") (target = "ldap:///ou=accounts,ou=%s,ou=eGW,%s") (version 3.0;acl "Asterisk/eGW account list access";allow (read,compare,search)(userdn = "ldap:///uid=asterisk,ou=Special Users,%s");)' % (dom, basedn, basedn),
        '(targetattr != "userPKCS12 || userPassword") (target = "ldap:///ou=accounts,ou=%s,ou=eGW,%s") (version 3.0;acl "System/eGW account list access";allow (read,compare,search) (userdn = "ldap:///uid=*,ou=People,%s");)' % (dom, basedn, basedn)]),
    ('ou=personal,ou=contacts,ou=%s,ou=eGW,%s' % (dom, basedn),[
        '(targetattr = "*") (target = "ldap:///cn=($dn),ou=personal,ou=contacts,ou=%s,ou=eGW,%s") (version 3.0;acl "System/eGW personal addressbook access";allow (read,compare,search) (userdn = "ldap:///uid=[$dn],ou=People,%s");)' % (dom, basedn, basedn),
        '(targetattr = "*") (target = "ldap:///cn=($dn),ou=personal,ou=contacts,ou=%s,ou=eGW,%s") (version 3.0;acl "eGW personal addressbook access";allow (read,compare,search,write,delete,add)(userdn = "ldap:///uid=[$dn],ou=accounts,ou=%s,ou=eGW,%s");)' % (dom, basedn, dom, basedn)]),
    ('ou=shared,ou=contacts,ou=%s,ou=eGW,%s' % (dom, basedn),[
        '(targetattr = "*") (target = "ldap:///($dn),ou=shared,ou=contacts,ou=%s,ou=eGW,%s") (version 3.0;acl "eGW group addressbook access";allow (read,compare,search,write,delete,add)(groupdn = "ldap:///[$dn],ou=groups,ou=%s,ou=eGW,%s");)' % (dom, basedn, dom, basedn),
        '(targetattr = "*") (target = "ldap:///($dn),ou=shared,ou=contacts,ou=%s,ou=eGW,%s") (version 3.0;acl "System/eGW group addressbook access";allow (read,compare,search) (groupdn = "ldap:///[$dn],ou=sasl-groups,ou=%s,ou=eGW,%s");)' % (dom, basedn, dom, basedn)]),
    ('ou=groups,ou=%s,ou=eGW,%s' % (dom, basedn),[
        '(targetattr = "objectClass || member") (target = "ldap:///cn=*,ou=groups,ou=%s,ou=eGW,%s") (version 3.0;acl "Apache/eGW group list access";allow (read,compare,search)(userdn = "ldap:///uid=apache, ou=Special Users,%s");)' % (dom, basedn, basedn)]),
    ('ou=Computers,' + basedn,[
        '(targetattr != "userPKCS12 || userPassword") (target = "ldap:///ou=Computers,%s") (version 3.0;acl "Anonymous access within domain";allow (read,compare,search)(userdn = "ldap:///anyone") and (dns="localhost" or dns="%s" or dns="*.%s");)' % (basedn, dnsdom, dnsdom)])
)

def addouent(ds,dn):
    pdns = [dn]
    while len(pdns) > 0:
        dn = pdns.pop()
        ent = Entry(dn)
        ent.setValues('objectclass', 'organizationalUnit')
        try:
            ds.add_s(ent)
            print "added entry", ent.dn
        except ldap.ALREADY_EXISTS:
            continue
        except ldap.NO_SUCH_OBJECT:
            pdns.append(dn)
            rdns = ldap.explode_dn(dn)
            pdn = ','.join(rdns[1:])
            pdns.append(pdn)
        except Exception, e:
            print "Could not add entry", ent.dn, str(e)
            raise e

for dn,acilist in dn2aci:
    while True:
        try:
            mod = [(ldap.MOD_REPLACE, 'aci', acilist)]
            print "adding acis to", dn
            ds.modify_s(dn, mod)
            break
        except ldap.NO_SUCH_OBJECT:
            print "adding missing entry", dn
            addouent(ds, dn)
            # and try the mod again

conn = DSAdmin(host1, port1)
#conn2 = DSAdmin(host1, port1)
page_size = 2
lc = SimplePagedResultsControl(
  ldap.LDAP_CONTROL_PAGE_OID,True,(page_size,'')
)

#conns = (conn, conn2)
conns = (conn,)
lenconns = len(conns)

for ii in xrange(0, 10):
    c = conns[ii % lenconns]
    msgid = c.search_ext(basedn, ldap.SCOPE_SUBTREE, serverctrls=[lc])
    pages = 1
    while True:
        print "Getting page", pages
        rtype, rdata, rmsgid, serverctrls = c.result3(msgid)
        pctrls = [
            pc
            for pc in serverctrls
            if pc.controlType == ldap.LDAP_CONTROL_PAGE_OID
            ]
        if pctrls:
            pages = pages + 1
            est, cookie = pctrls[0].controlValue
            if cookie:
                lc.controlValue = (page_size, cookie)
                msgid = c.search_ext(basedn, ldap.SCOPE_SUBTREE, serverctrls=[lc])
            else:
                print "Found", pages, "pages"
                break
        else:
            print "Server did not return Simple Paged control!!!"
            break
    else:
        print "Warning:  Server ignores Simple Paged control."
        break
