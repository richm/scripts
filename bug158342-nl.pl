
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
$h1 = createInstance({
	cfgdshost => $host1,
	cfgdsport => $cfgport,
	cfgdsuser => 'admin',
	cfgdspwd => 'admin',
	newrootpw => 'password',
	newhost => $host1,
	newport => $cfgport+20,
	newinst => 'h1',
	newsuffix => 'dc=example,dc=com',
	verbose => 1
});
delete $ENV{USE_DBX};

#$ENV{USE_DBX} = 1;
$h2 = createInstance({
	cfgdshost => $host1,
	cfgdsport => $cfgport,
	cfgdsuser => 'admin',
	cfgdspwd => 'admin',
	newrootpw => 'password',
	newhost => $host2,
	newport => $cfgport+30,
	newinst => 'h2',
	newsuffix => 'dc=example,dc=com',
	verbose => 1
});
delete $ENV{USE_DBX};

my $suffix = "o=my_suffix.com";

print "Create suffixes on the mux\n";
createOrgEntry($h1, $suffix);
createOrgEntry($h2, $suffix);

print "Set up chaining . . .\n";
$m1->setupChaining($h1, $suffix);
$m1->setupChaining($h2, $suffix);

print "Add the acis on the farms . . .\n";
my $binddn = "cn=chaining user,cn=config";
my $aci1 = "(targetattr = \"*\") (version 3.0;acl \"bind_user\";allow (all)(userdn = \"ldap:///$binddn\");)";
my $aci2 = "(targetattr = \"*\") (version 3.0;acl \"All\";allow (all)(userdn = \"ldap:///*,$suffix\");)";
my $mesg = $h1->modify($suffix, add => {aci => [ $aci1, $aci2 ]});
check_mesg($mesg, "Could not add acis to h1");
$mesg = $h2->modify($suffix, add => {aci => [ $aci1, $aci2 ]});
check_mesg($mesg, "Could not add acis to h2");

print "Try a search\n";
$mesg = $m1->search(base   => $suffix,
	                scope  => 'base',
	                filter => '(objectclass=*)');
check_mesg($mesg, "Could not search for $suffix");
my $ent = $mesg->shift_entry;
$ent->dump;

# creates the backend, suffix, and entry for o= style suffixes
sub createOrgEntry {
	my ($conn, $suffix) = @_;
	my $rc = $conn->addSuffix($suffix);
	if ($rc) {
		print "Couldn't add chaining suffix $suffix: $rc: " . $conn->getErrorString(), "\n";
	} else {
		my $entry = new Net::LDAP::Entry();
		$entry->dn($suffix);
		$entry->add('objectclass' => ['top', 'organization']);
		my $mesg = $conn->add($entry);
		check_mesg($mesg, "Error adding new suffix entry $suffix");
	}
}
