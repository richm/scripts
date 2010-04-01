use Net::LDAP;
use Net::LDAP::Util qw(canonical_dn ldap_explode_dn ldap_error_name);
use Net::LDAP::Constant qw(:all);
use Net::LDAP::Control;
use Net::LDAP::Control::PersistentSearch;
use Net::LDAP::Control::EntryChange;
use Convert::ASN1;

my $host = 'localhost';
my $port = 1130;
my $basedn = "dc=example,dc=com";
my $rootdn = "cn=directory manager";
my $rootpw = "password";

my $reqctrl = Convert::ASN1->new;
$reqctrl->prepare(q<

         controlValue ::= SEQUENCE OF DerefSpec

         DerefSpec ::= SEQUENCE {
             derefAttr       AttributeDescription,    -- with DN syntax
             attributes      AttributeList }

         AttributeList ::= SEQUENCE OF AttributeDescription

         LDAPString ::= OCTET STRING

         AttributeDescription ::= LDAPString

>) || die "Could not prepare request control: " . $reqctrl->{error};

my $resctrl = Convert::ASN1->new;
$resctrl->prepare(q<
         controlValue ::= SEQUENCE OF DerefRes

         DerefRes ::= SEQUENCE {
             derefAttr       AttributeDescription,
             derefVal        LDAPDN,
             attrVals        [0] PartialAttributeList OPTIONAL }

         PartialAttributeList ::= SEQUENCE OF PartialAttribute

         PartialAttribute ::= SEQUENCE {
             type       AttributeDescription,
             vals       SET OF AttributeValue }

         AttributeDescription ::= LDAPString

         LDAPDN ::= LDAPString

         LDAPString ::= OCTET STRING -- UTF8String ??

         AttributeValue ::= OCTET STRING
>) || die "Could not prepare response control: " . $resctrl->{error};

# my $testreq = (
#     controlValue => [
#         { derefAttr => 'derefattr1',
#           attributes => [ 'val1', 'val2' ] },
#         { derefAttr => 'derefattr2',
#           attributes => [ 'val3', 'val4' ] }
#     ]
# );

my $testreq = (
    controlValue => [
        { derefAttr => 'member',
          attributes => [ 'roomNumber', 'doesnotexist', 'nsRole', 'nsUniqueID' ] }
    ]
);

my $asn = $reqctrl->find('controlValue');
my $derefctrlval = $asn->encode($testreq);
# my $pval;
# foreach (split //, $derefctrlval) {
#     $pval = $pval . " " . ord($_);
# }
# print "encoded val $pval\n";

my $ldap = Net::LDAP->new("$host:$port");

# bind to a directory with dn and password
$mesg = $ldap->bind($rootdn, password => $rootpw);
$mesg->code && die $mesg->error;

my $derefctrl = Net::LDAP::Control->new(
    type       => "1.3.6.1.4.1.4203.666.5.16",
    critical   => 0,
    value      => $derefctrlval
);

my $persist = Net::LDAP::Control::PersistentSearch->new( changeTypes => 15,
                                                         changesOnly => 0,
                                                         returnECs => 1 );

$asn = $resctrl->find('controlValue');
sub handler {
    my $mesg = shift;
    my $entry = shift;
    my $ctrl = ($mesg->control("1.3.6.1.4.1.4203.666.5.16"))[0];
    my $ectrl = ($mesg->control(LDAP_CONTROL_ENTRYCHANGE))[0];
#     print "control = ", $ctrl, "\n";
#     for my $key (keys %{$ctrl}) {
#         print "  control $key = ", $ctrl->{$key}, "\n";
#     }
    my $ctrlval = $asn->decode($ctrl->{value});
#    print "ctrlval = $ctrlval\n";
    foreach (@{$ctrlval}) {
#        print " $_\n";
        print "derefAttr = ", $_->{derefAttr}, "\n";
        print "derefDN = ", $_->{derefVal}, "\n";
        if (exists($_->{attrVals}) && defined($_->{attrVals})) {
            foreach my $href (@{$_->{attrVals}}) {
                print " attr = ", $href->{type}, " vals = ", @{$href->{vals}}, "\n";
            }
        }
    }
    print "Entry Change: ", $ectrl->changeType."\t".$entry->dn."\n";
    if ($entry) {
        $entry->dump;
    } else {
        print "Result: ", $mesg->code, "\n";
    }
}

$mesg = $ldap->search(base       => "cn=everyone,$basedn",
                      scope      => "base",
                      filter     => "(objectclass=*)",
                      attrs      => ['cn'],
                      control    => [$derefctrl,$persist],
                      callback   => \&handler
                      );
$mesg->code and die $mesg->error;

print "#" x 80, "\n";

my $userdn = "uid=scarter,ou=people,$basedn";
my $userpw = "sprain";
$mesg = $ldap->bind($userdn, password => $userpw);
$mesg->code && die $mesg->error;

$mesg = $ldap->search(base       => "cn=everyone,$basedn",
                      scope      => "base",
                      filter     => "(objectclass=*)",
                      attrs      => ['cn'],
                      control    => [$derefctrl,$persist],
                      callback   => \&handler
                      );
$mesg->code and die $mesg->error;

# foreach my $entry ($mesg->entries) {
#     $entry->dump;
# }

# $mesg = $ldap->unbind;
