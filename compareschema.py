
import ldap
from ldap.cidict import cidict
from ldap.schema import SubSchema
import ldif
import sys
import pprint

attrclass = ldap.schema.models.AttributeType
occlass = ldap.schema.models.ObjectClass

def ochasattr(subschema, oc, mustormay, attr, key):
    """See if the oc and any of its parents and ancestors have the
    given attr"""
    rc = False
    if not key in oc.__dict__:
        dd = cidict()
        for ii in oc.__dict__[mustormay]:
            dd[ii] = ii
        oc.__dict__[key] = dd
    if attr in oc.__dict__[key]:
        rc = True
    else:
        # look in parents
        for noroid in oc.sup:
            ocpar = subschema.get_obj(occlass, noroid)
            assert(ocpar)
            rc = ochasattr(subschema, ocpar, mustormay, attr, key)
            if rc:
                break
    return rc

def ochasattrs(subschema, oc, mustormay, attrs):
    key = mustormay + "dict"
    ret = []
    for attr in attrs:
        if not ochasattr(subschema, oc, mustormay, attr, key):
            ret.append(attr)
    return ret

def mycmp(v1, v2):
    v1ary, v2ary = [v1], [v2]
    if isinstance(v1, list) or isinstance(v1, tuple):
        v1ary, v2ary = list(set([x.lower() for x in v1])), list(set([x.lower() for x in v2]))
    if not len(v1ary) == len(v2ary):
        return False
    for v1, v2 in zip(v1ary, v2ary):
        if isinstance(v1, basestring):
            if not len(v1) == len(v2):
                return False
        if not v1 == v2:
            return False
    return True

def ocgetdiffs(ldschema, oc1, oc2):
    fields = ['obsolete', 'names', 'desc', 'must', 'may', 'kind', 'sup']
    ret = ''
    for field in fields:
        v1, v2 = oc1.__dict__[field], oc2.__dict__[field]
        if field == 'may' or field == 'must':
            missing = ochasattrs(ldschema, oc1, field, oc2.__dict__[field])
            if missing:
                ret = ret + '\t%s is missing %s\n' % (field, missing)
            missing = ochasattrs(ldschema, oc2, field, oc1.__dict__[field])
            if missing:
                ret = ret + '\t%s is missing %s\n' % (field, missing)
        elif not mycmp(v1, v2):
            ret = ret + '\t%s differs: [%s] vs. [%s]\n' % (field, oc1.__dict__[field], oc2.__dict__[field])
    return ret

def atgetparfield(subschema, at, field):
    v = None
    for nameoroid in at.sup:
        atpar = subschema.get_obj(attrclass, nameoroid)
        assert(atpar)
        v = atpar.__dict__.get(field, atgetparfield(subschema, atpar, field))
        if v is not None:
            break
    return v

def atgetdiffs(ldschema, at1, at2):
#    fields = ['names', 'desc', 'obsolete', 'sup', 'equality', 'ordering', 'substr', 'syntax', 'syntax_len', 'single_value', 'collective', 'no_user_mod', 'usage']
    fields = ['names', 'desc', 'obsolete', 'sup', 'equality', 'ordering', 'substr', 'syntax', 'single_value', 'collective', 'no_user_mod', 'usage']
    ret = ''
    for field in fields:
        v1 = at1.__dict__.get(field) or atgetparfield(ldschema, at1, field)
        v2 = at2.__dict__.get(field) or atgetparfield(ldschema, at2, field)
        if not mycmp(v1, v2):
            ret = ret + '\t%s differs: [%s] vs. [%s]\n' % (field, at1.__dict__[field], at2.__dict__[field])
    return ret

# read and parse each schema file given on the command line
allattrs = ldap.cidict.cidict()
dupattrs = ldap.cidict.cidict()
allocs = ldap.cidict.cidict()
dupocs = ldap.cidict.cidict()
alloids = {}
dupoids = {}

# these are schema elements present in files but missing from ldap
missingfromld = []
# these are schema elements present in ldap but missing from files
missingfromfiles = []
# these are schema elements which differ
# key is oid - val is a list - 0 is ld version, 1 is file version
atdiffs = {}
ocdiffs = {}

dn, ldschema = ldap.schema.subentry.urlfetch(sys.argv[1])
retval = 0
ocoids = ldap.cidict.cidict()
atoids = ldap.cidict.cidict()

for myfile in sys.argv[2:]:
    try:
        dn, sc = ldap.schema.subentry.urlfetch(myfile)
    except IndexError:
        print "skipping file due to parsing errors", myfile
        continue
    for oid in sc.listall(occlass):
        se = sc.get_obj(occlass, oid)
        assert(se)
        (oldse, oldfile) = ocoids.get(oid, (None, None))
        if oldse:
            print "replacing oc oid %s name %s from file %s with def from file %s" % \
                (oid, se.names[0], oldfile, myfile)
        ocoids[oid] = (se, myfile)
    for oid in sc.listall(attrclass):
        se = sc.get_obj(attrclass, oid)
        assert(se)
        (oldse, oldfile) = atoids.get(oid, (None, None))
        if oldse:
            print "replacing at oid %s name %s from file %s with def from file %s" % \
                (oid, se.names[0], oldfile, myfile)
        atoids[oid] = (se, myfile)

for oid, (se, myfile) in ocoids.iteritems():
    ldse = ldschema.get_obj(occlass, oid)
    if not ldse:
        # try case insensitive match - slow!
        for ldoid in ldschema.listall(occlass):
            if ldoid.lower() == oid.lower():
                ldse = ldschema.get_obj(occlass, ldoid)
                break
    if not ldse:
        print "objectclass in %s but not in %s: %s" % (myfile, sys.argv[1], se)
        missingfromld.append(se)
        retval = 1
        continue
    ret = ocgetdiffs(ldschema, ldse, se)
    if ret:
        sys.stdout.write("name %s oid %s\n%s" % (se.names[0], oid, ret))
        ocdiffs[oid] = [se, ldse]
        retval = 1

for oid, (se, myfile) in atoids.iteritems():
    ldse = ldschema.get_obj(attrclass, oid)
    if not ldse:
        # try case insensitive match - slow!
        for ldoid in ldschema.listall(attrclass):
            if ldoid.lower() == oid.lower():
                ldse = ldschema.get_obj(attrclass, ldoid)
                break
    if not ldse:
        print "attributetype in %s but not in %s: %s" % (myfile, sys.argv[1], se)
        missingfromld.append(se)
        retval = 1
        continue
    ret = atgetdiffs(ldschema, ldse, se)
    if ret:
        sys.stdout.write("name %s oid %s\n%s" % (se.names[0], oid, ret))
        atdiffs[oid] = [se, ldse]
        retval = 1

if retval == 0:
    print "END OK - schema matches"
else:
    print "END ERROR - one or more schema mismatches"
sys.exit(retval)
