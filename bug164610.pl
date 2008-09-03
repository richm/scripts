
use NDSAdminNL qw(my_ldap_url_parse createInstance check_mesg createAndSetupReplica);

my $sroot = $ENV{SERVER_ROOT};

my $host1 = "localhost.localdomain";

my $host2 = $host1;
my $cfgport = 7100;

my ($m1, $m2, $h1, $h2, $c1, $c2);

#$ENV{USE_DBX} = 1;
$m1 = createInstance({
	cfgdshost => $host1,
	cfgdsport => $cfgport,
	cfgdsuser => 'admin',
	cfgdspwd => 'admin',
	newrootpw => 'password',
	newhost => $host1,
	newport => $cfgport+10,
	newinst => 'm1',
	newsuffix => 'dc=example,dc=com',
	verbose => 1
});
delete $ENV{USE_DBX};

my $initfile = "$m1->{sroot}/slapd-$m1->{inst}/ldif/Example.ldif";
$m1->importLDIF($initfile, 0, "userRoot", 1);

for (my $ii = 1; $ii <= 1000; ++$ii) {
    my $dn = "ou=testview$ii, dc=example, dc=com";
    my $ent = new Net::LDAP::Entry;
    $ent->dn($dn);
    $ent->add("objectclass", [ 'nsview', 'organizationalUnit' ]);
    $ent->add('nsviewfilter', '(objectclass=person)');
    my $mesg = $m1->add($ent);
    check_mesg($mesg, "Could not add entry " . $ent->dn);
    $mesg = $m1->delete($dn);
    check_mesg($mesg, "Could not delete entry $dn");
    print "$ii ";
    if (($ii % 10) == 0) {
        print "\n";
    }
}
