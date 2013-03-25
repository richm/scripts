from bug_harness import DSAdminHarness as DSAdmin
from dsadmin import Entry

"""
    An harness for bug replication.

"""
import os


class DSAdminHarness(DSAdmin):
    """Harness wrapper around dsadmin.

       Specialize the DSAdmin behavior (No, I don't care about Liskov ;))
    """
    def setupSSL(self, secport=0, sourcedir=os.environ['SECDIR'], secargs=None):
        """Bug scripts requires SECDIR."""
        return DSAdmin.setupSSL(self, secport, sourcedir, secargs)

    def setupAgreement(self, repoth, args):
        """Set default replia credentials """
        args.setdefault('binddn', REPLBINDDN)
        args.setdefault('bindpw', REPLBINDPW)

        return DSAdmin.setupAgreement(self, repoth, args)
