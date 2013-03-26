"""Utilities for DSAdmin. 

    TODO put them in a module!
"""
try:
    from subprocess import Popen, PIPE
    HASPOPEN = True
except ImportError:
    import popen2
    HASPOPEN = False
    
import socket
import ldap
import re

def normalizeDN(dn, usespace=False):
    # not great, but will do until we use a newer version of python-ldap
    # that has DN utilities
    ary = ldap.explode_dn(dn.lower())
    joinstr = ","
    if usespace:
        joinstr = ", "
    return joinstr.join(ary)


def escapeDNValue(dn):
    '''convert special characters in a DN into LDAPv3 escapes e.g.
    "dc=example,dc=com" -> \"dc\=example\,\ dc\=com\"'''
    for cc in (' ', '"', '+', ',', ';', '<', '>', '='):
        dn = dn.replace(cc, '\\' + cc)
    return dn


def escapeDNFiltValue(dn):
    '''convert special characters in a DN into LDAPv3 escapes
    for use in search filters'''
    for cc in (' ', '"', '+', ',', ';', '<', '>', '='):
        dn = dn.replace(cc, '\\%x' % ord(cc))
    return dn


def suffixfilt(suffix):
    nsuffix = normalizeDN(suffix)
    escapesuffix = escapeDNFiltValue(nsuffix)
    spacesuffix = normalizeDN(nsuffix, True)
    filt = '(|(cn=%s)(cn=%s)(cn=%s)(cn="%s")(cn="%s")(cn=%s)(cn="%s"))' % (escapesuffix, nsuffix, spacesuffix, nsuffix, spacesuffix, suffix, suffix)
    return filt


def isLocalHost(hname):
    # first see if this is a "well known" local hostname
    if hname == 'localhost' or hname == 'localhost.localdomain':
        return True

    # first lookup ip addr
    ipadr = None
    try:
        ipadr = socket.gethostbyname(hname)
    except Exception, e:
        pass
    if not ipadr:
        print "Error: no IP Address for", hname
        return False

    # next, see if this IP addr is one of our
    # local addresses
    thematch = re.compile('inet addr:' + ipadr)
    found = False
    if HASPOPEN:
        p = Popen(['/sbin/ifconfig', '-a'], stdout=PIPE)
        child_stdout = p.stdout
    else:
        child_stdout, child_stdin = popen2.popen2(['/sbin/ifconfig', '-a'])
    for line in child_stdout:
        if re.search(thematch, line):
            found = True
            break
    if HASPOPEN:
        p.wait()
    return found


def getfqdn(name=''):
    return socket.getfqdn(name)


def getdomainname(name=''):
    fqdn = getfqdn(name)
    index = fqdn.find('.')
    if index >= 0:
        return fqdn[index + 1:]
    else:
        return fqdn


def getdefaultsuffix(name=''):
    dm = getdomainname(name)
    if dm:
        return "dc=" + dm.replace('.', ',dc=')
    else:
        return 'dc=localdomain'

def is_a_dn(dn):
    """Returns True if the given string is a DN, False otherwise."""
    return (dn.find("=") > 0)

def get_sbin_dir(sroot, prefix):
    if sroot:
        return "%s/bin/slapd/admin/bin" % sroot
    elif prefix:
        return "%s/sbin" % prefix
    return "/usr/sbin"
