package NDSAdminNL;

use Socket;
use Sys::Hostname;
use IPC::Open2;
use Symbol;
use URI::Escape;
use MIME::Base64;
use Cwd;
use File::Basename;

use Net::LDAP;
use Net::LDAP::Util qw(canonical_dn ldap_explode_dn ldap_error_name);
use Net::LDAP::Constant qw(:all);

require    Exporter;
@ISA       = qw(Exporter Net::LDAP);
@EXPORT    = qw(getFQDN getdomainname createAndSetupReplica replicaSetupAll
			  createInstance defaultadmindomain defaultsuffix printRUV
			  parseCSNs compareCSNs compareRUVs $MASTER_TYPE $HUB_TYPE $LEAF_TYPE
			  parseCSN getTSDiff printTSDiff removeOtherInstance
			  check_mesg my_ldap_explode_dn normalizeDN my_ldap_url_parse);

my $isNT = -d '\\';

my $REPLBINDDN;
my $REPLBINDCN;
my $REPLBINDPW;

sub hex_unescape {
	my $s = shift;
	$s =~ s/%([A-Fa-f0-9]{2})/chr(hex($1))/eg; # unescape
	return $s;
}

sub my_ldap_url_parse {
	my $url = shift;
	my $href = {};
	if ($url =~ m|^(ldap.?)://([^/]+)/([^\?]+)?\?([^\?]+)?\?([^\?]+)?\?([^\?]+)?|) {
		$href->{meth} = $1;
		# $2 includes port, if present
		$href->{host} = hex_unescape($2);
		# $href->{port} = $3;
		$href->{dn} = hex_unescape($3);
		$href->{attr} = hex_unescape($4);
		$href->{scope} = hex_unescape($5);
		$href->{filter} = hex_unescape($6);
	} else {
		print "invalid url : $url\n";
		return $href;
	}

	if ($href->{host} =~ /:(\d+)$/) {
		$href->{host} = $`;
		$href->{port} = $1;
	}
	if ($href->{attr}) { # convert to array
		my @ary = split(/,/, $href->{attr});
		$href->{attr} = \@ary;
	}
	return $href;
}

sub normalizeDN {
	my $dn = shift;
	return lc(canonical_dn($dn, casefold => 'lower'));
}

# if args is 1, return an array of values, no attribute name or '='
sub my_ldap_explode_dn {
	my ($dn, $valuesOnly) = @_;
	my $ary = ldap_explode_dn($dn, casefold => 'none');
	my @rdns;
	while (@$ary) {
		my $href = shift @$ary;
		while (my ($key, $val) = each %$href) {
			if ($valuesOnly) {
				push @rdns, $val;
			} else {
				push @rdns, $key . '=' . $val;
			}
		}
	}
	return @rdns;
}

sub getFQDN {
# return fully qualified host and domain name
# ex : hippo.example.com
# if the hostname from hostname() is not FQDN, find the first alias
# which matches the hostname which is also FQDN e.g.
# if given hippo, the $name might be realhost.example.com, but one of the aliases
# may be hippo.example.com - prefer the latter over the former since it matches
# the hostname
  my $hostname = shift;
  my $hrefalias = shift;

  return 'localhost' if (!$hostname && $ENV{LOCALHOSTFORHOSTNAME});
  return 'localhost' if ($hostname eq 'localhost' && $ENV{LOCALHOSTFORHOSTNAME});

  my $fqdn;
  if ($isNT) { # gethostbyname on NT messes up ldap_simple_bind_s
	$hostname = $hostname || `hostname`; # hostname on NT does not give FQDN
  } else {
	$hostname = $hostname || hostname();

# find the alias that most closely matches the hostname
	my ($name, $aliases, @rest) = gethostbyname($hostname);
	if ($aliases) {
	  my @alias = split(/\s+/, $aliases);
	  my $max = 1; # must have at least 1 domain component
	  for (@alias) {
		$hrefalias->{$_} = $_ if ($hrefalias);
		my $n = tr/\./\./; # count dots in name
		if (($n >= $max) && /^$hostname/) {
		  $max = $n;
		  $fqdn = $_;
		}
	  }
	}
  }

  if (!$fqdn) {
	if (open(NSLOOKUP, "nslookup $hostname|")) {
	  my $name;
	  sleep 1; # allow pipe to fill with data
	  while (<NSLOOKUP>) {
		chop;
		# use aliases if available, and the alias is an FQDN, and the
		# the alias is a close match to our hostname
		if (/^Aliases:\s*/) {
		  my $alias = $';
		  $hrefalias->{$alias} = $alias if ($hrefalias);
		  if ($alias =~ /\./ && $alias =~ /^$hostname/) {
			$fqdn = $alias;
			last;
		  }
		}
		# if no alias, just use the name
		if (/^Name:\s*/) {
		  $name = $';
		  $hrefalias->{$name} = $name if ($hrefalias);
		}
	  }
	  close NSLOOKUP;
	  if (!$fqdn && $name) {
		$fqdn = $name;
	  }
	}
  }

  # if we could not find a match, return the hostname if it contains
  # domain components or return the $name
  if (!$fqdn) {
	if ($hostname =~ /\./) { # perhaps the hostname is already fqdn
	  $fqdn = $hostname;
	} elsif ($name =~ /\./) { # try the canonical name
	  $fqdn = $name;
	} elsif (my $dmn = `domainname`) { # append the domain name
	  $fqdn = $hostname.$dmn;
	} else { # punt
	  $fqdn = $hostname;
	}
  }

  return $fqdn;
}

sub getdomainname {
  my $h = getFQDN(shift);
  # if $h begins with word. ...
  if ($h =~ /^.+?\./) {
	# ... return everything after word.
	return $'; # ' fix comment
  }
  return "";
}

sub defaultadmindomain {
  return (getdomainname(shift) || "example.com");
}

sub defaultsuffix {
  my $dm = getdomainname(shift);
  return "dc=example, dc=com" if (! $dm);
  my @dc = split(/\./, $dm);
  map { $_ = "dc=$_" } @dc;
  return join(',', @dc);
}

#########################################
# OVERRIDE methods go here ##############
#########################################
sub rebindProc {
  print "In rebind proc, args = @_\n" if ($verbose);
  return ($main::binddn, $main::bindpw, LDAP_AUTH_SIMPLE);
}

# returns the rebind proc subroutine
sub genRebindProc {
  my ($dn, $pwd, $auth, $verbose) = @_;
  $auth = LDAP_AUTH_SIMPLE if (!$auth);
  return sub {
	print "In rebind proc, args = @_\n" if ($verbose);
	return ($dn, $pwd, $auth);
  };
}

sub toString {
  my $self = shift;
  return $self->{host} . ":" . $self->{port};
}

sub toLDAPURL {
  my $self = shift;
  return "ldap://" . $self->{host} . ":" . $self->{port} . "/";
}

# mesg is the Net::LDAP::Message returned from the api call
# text is a string to print with the error message
# ignore is a hash - the keys are ldap error codes to ignore
sub check_mesg {
	my ($mesg, $txt, $ignore) = @_;
	my $code = $mesg->code;
# 	if ($ignore) {
# 		foreach my $val (keys %$ignore) {
# 			print "ignoring code $val\n";
# 		}
# 		print "returned code = $code\n";
# 	}
	if (($code != LDAP_SUCCESS) && (!$ignore || !$ignore->{ldap_error_name($code)})) {
		my ($pkg, $file, $line) = caller;
		die $txt . ": code " . $code . " error [" . $mesg->error() . "] at $pkg:$file:$line";
	}

	return $code;
}

sub init {
  my $self = shift;
  my $code;
  if ($self->{binddn} && $self->{bindpasswd}) {
	$mesg = $self->bind($self->{binddn},
						password => $self->{bindpasswd},
						version => 3);
	$code = check_mesg($mesg, "Could not bind to " . $self->toString() . " as " . $self->{binddn},
					   $self->{ignore});
  } else {
	$mesg = $self->bind; # anon
	$code = check_mesg($mesg, "Could not bind as anonymous", $self->{ignore});
  }

  return $code;
}

sub new {
  my $type = shift;
  my $self = Net::LDAP->new(@_);
  if (!$self) {
	  return $self;
  }
  my $host = shift if @_ % 2;
  my %ret = @_;
  my $mesg;

  $self->{host} = $host;
  $self->{port} = $ret{port} || 389;
  $self->{binddn} = $ret{binddn};
  $self->{bindpasswd} = $ret{bindpasswd};
  $self->{ignore} = $ret{ignore};

  # see if binddn is a dn or a uid that we need to lookup
  if ($self->{binddn} && ($self->{binddn} !~ /\=/)) {
	$mesg = $self->bind; # anon
    check_mesg($mesg, "Could not anon bind to lookup " . $self->{binddn});
	$mesg = $self->search(base   => "o=NetscapeRoot",
						  filter => "(uid=" . $self->{binddn} . ")",
						  attrs  => ['uid']);
    check_mesg($mesg, "Could not lookup " . $self->{binddn});
	my $cfgent = $mesg->shift_entry;
	if ($cfgent) {
	  $self->{binddn} = $cfgent->dn;
	} else {
	  print "Error: could not find ", $self->{"binddn"}, " under o=NetscapeRoot\n";
	}
  }

  $self = bless $self, $type;
  my $code = $self->init;
  if ($code == LDAP_SUCCESS) {
	$self->initPart2();
  }

  return $self;
}

# we should do this any time we rebind - the user may have created the initial
# connection as anonymous, then did a rebind as an administrative user, so we
# need to read the information we could not read before
sub initPart2 {
  my $self = shift;
  # set the other things like the instance name and server root, but not if
  # the connection is anonymous
  if ($self->{binddn} && length($self->{binddn}) && !$self->{sroot}) {
	$mesg = $self->search(base   => "cn=config",
						  scope  => 'base',
						  filter => "(objectclass=*)",
						  attrs  => [ 'nsslapd-instancedir', 'nsslapd-errorlog' ]);
    check_mesg($mesg, "Could not read cn=config",
			   # ignore these errors
			   { LDAP_INSUFFICIENT_ACCESS => LDAP_INSUFFICIENT_ACCESS,
				 LDAP_CONNECT_ERROR => LDAP_CONNECT_ERROR });
	my $cfgent = $mesg->shift_entry();
	if ($cfgent) {
	  my $instdir = $cfgent->get_value('nsslapd-instancedir');
	  if ($instdir =~ m|(.*)[\\/]slapd-(\w+)$|) {
		$self->{sroot} = $1;
		$self->{inst} = $2;
	  } else {
		print "Error: could not parse instance dir $instdir\n";
	  }
	  $self->{errlog} = $cfgent->get_value('nsslapd-errorlog');
	  if (!$self->{isLocal}) {
        # possibly dangerous - many machines could have /usr/netscape/slapd-foo
		if (-d $instdir) { # does instance dir exist on this machine?
		  $self->{isLocal} = 1;
		} else {
		  $self->{isLocal} = 0;
		}
	  }
	}
  }
}

# this does not check to see if the suffix already has backends, because
# this function can also be used to create multiple backends for entry
# distribution
# call getBackendsForSuffix before calling this function if you need
# to make sure the suffix does not already have backends
# returns the name (the cn) of the backend just created or 0
sub setupBackend {
  my ($self, $suffix, $binddn, $bindpw, $urls, $attrvals) = @_;
  my $ldbmdn = "cn=ldbm database, cn=plugins, cn=config";
  my $chaindn = "cn=chaining database, cn=plugins, cn=config";
  my $dnbase;
  my $benamebase;
  # figure out what type of be based on args
  if ($binddn && $bindpw && $urls) { # its a chaining be
	$benamebase = "chaindb";
	$dnbase = $chaindn;
  } else { # its a ldbm be
	$benamebase = "localdb";
	$dnbase = $ldbmdn;
  }
  my $nsuffix = normalizeDN($suffix);
  my $rc = LDAP_ALREADY_EXISTS;
  my $benum = 1;
  my $mesg;
  while ($rc == LDAP_ALREADY_EXISTS) {
	$entry = new Net::LDAP::Entry;
	my $cn = $benamebase . $benum; # e.g. localdb1
	my $dn = "cn=$cn, $dnbase";
	$entry->dn($dn);
	$entry->add('objectclass' => ['top', 'extensibleObject', 'nsBackendInstance']);
	$entry->add('cn' => $cn);
	$entry->add('nsslapd-suffix' => $nsuffix);
	if ($binddn && $bindpw && $urls) { # its a chaining be
	  $entry->add('nsfarmserverurl' => $urls);
	  $entry->add('nsmultiplexorbinddn' => $binddn);
	  $entry->add('nsmultiplexorcredentials' => $bindpw);
	} else { # set ldbm parameters, if any
#	  $entry->add('nsslapd-cachesize' => '-1');
#	  $entry->add('nsslapd-cachememsize' => '2097152');
	}
	while ($attrvals && (my ($attr, $val) = each %{$attrvals})) { # add more attrs and values
	  print "adding $attr = $val to entry $dn\n";
	  $entry->add($attr => $val);
	}
	$entry->dump;
	$mesg = $self->add($entry);
	check_mesg($mesg, "Error adding be entry " . $dn,
			   {LDAP_ALREADY_EXISTS => LDAP_ALREADY_EXISTS});
	$rc = $mesg->code();
	if ($rc == LDAP_SUCCESS) {
	  $mesg = $self->search(base => $dn, scope => "base", filter => "(objectclass=*)");
	  check_mesg($mesg, "Error getting new be entry " . $dn);
	  $entry = $mesg->shift_entry();
	  if (! $entry) {
		print "Entry $dn was added successfully, but I cannot search it\n";
		$rc = -1;
	  } else {
		$entry->dump;
		return $cn;
	  }
	} elsif ($rc == LDAP_ALREADY_EXISTS) { # that name exists
	  $benum++; # increment and try again
	}
  }

  return 0;
}

sub setupSuffix {
  my ($self, $suffix, $bename, $parent, $rc) = @_;
  my $nsuffix = normalizeDN($suffix);
  my $nparent = normalizeDN($parent) if ($parent);

  my $dn = "cn=\"$nsuffix\", cn=mapping tree, cn=config";
  my $mesg = $self->search(base   => "cn=mapping tree, cn=config",
						   scope  => "sub",
						   filter => "(|(cn=\"$suffix\")(cn=\"$nsuffix\"))");
  check_mesg($mesg, "Error searching for parent suffix");
  my $entry = $mesg->shift_entry();
  if (! $entry) {
	$entry = new Net::LDAP::Entry();
	$dn = "cn=\"$nsuffix\", cn=mapping tree, cn=config";
	$entry->dn($dn);
	$entry->add('objectclass' => ['top', 'extensibleObject', 'nsMappingTree']);
	$entry->add('cn' => "\"$nsuffix\"");
	$entry->add('nsslapd-state' => 'backend');
	$entry->add('nsslapd-backend' => $bename);
	$entry->add('nsslapd-parent-suffix'=> "\"$nparent\"") if ($parent);
	$mesg = $self->add($entry);
	check_mesg($mesg, "Error adding new suffix entry $dn");
	$mesg = $self->search(base => $dn, scope => "base", filter => "(objectclass=*)");
	check_mesg($mesg, "Error getting new suffix entry $dn");
	$entry = $mesg->shift_entry;
	if (! $entry) {
		print "Entry $dn was added successfully, but I cannot search it\n";
		$rc = -1;
	} else {
		$entry->dump;
	}
  }

  return $rc;
}

# given a suffix, return the mapping tree entry for it
sub getMTEntry {
  my ($self, $suffix, @attrs) = @_;
  my $nsuffix = normalizeDN($suffix);
  my $mesg = $self->search(base   => "cn=mapping tree,cn=config",
						   scope  => "one",
						   filter => "(|(cn=\"$suffix\")(cn=\"$nsuffix\"))",
						   attrs  => [@attrs]);
  check_mesg($mesg, "Error searching for mapping tree entry for $suffix");
  return $mesg->shift_entry;
}

# given a suffix, return a list of backend entries for that suffix
sub getBackendsForSuffix {
  my ($self, $suffix, @attrs) = @_;
  my $nsuffix = normalizeDN($suffix);
  my $mesg;
  $mesg = $self->search(base   => "cn=plugins,cn=config",
						scope  => "sub",
						filter => "(&(objectclass=nsBackendInstance)(|(nsslapd-suffix=$suffix)(nsslapd-suffix=$nsuffix)))",
						attrs  => [@attrs]);
  check_mesg($mesg, "Error searching for backends for suffix " . $nsuffix);
  return $mesg->entries();
}

# given a backend name, return the mapping tree entry for it
sub getSuffixForBackend {
  my ($self, $bename, @attrs) = @_;
  my $mesg = $self->search(base   => "cn=plugins,cn=config",
						   scope  => "sub",
						   filter => "(&(objectclass=nsBackendInstance)(cn=$_))",
						   attrs  => ['nsslapd-suffix']);
  check_mesg($mesg, "Error searching for be entry for $_");
  my $beent = $mesg->shift_entry;
  if ($beent) {
	my $suffix = $beent->get_value('nsslapd-suffix');
	return $self->getMTEntry($suffix, @attrs);
  }

  return 0;
}

sub addSuffix {
  my ($self, $suffix, $binddn, $bindpw, @urls) = @_;
  my @beents = $self->getBackendsForSuffix($suffix, qw(cn));
  my $bename;
  my @benames;
  # no backends for this suffix yet - create one
  if (!@beents) {
	if (!($bename = $self->setupBackend($suffix, $binddn, $bindpw, \@urls))) {
	  print "Couldn't create backend for $suffix\n";
	  return -1; # ldap error code handled already
	}
  } else { # use existing backend(s)
	for (@beents) {
		push @benames, $_->get_value('cn');
	}
	$bename = shift @benames;
  }

  my $parent = $self->findParentSuffix($suffix);
  if (my $rc = $self->setupSuffix($suffix, $bename, $parent)) {
	print "Couldn't create suffix for $bename $suffix " . $self->getErrorString(), "\n";
  }

  return $rc;
}

# specify the suffix (should contain 1 local database backend),
# the name of the attribute to index, and the types of indexes
# to create e.g. "pres", "eq", "sub"
sub addIndex {
  my ($self, $suffix, $attr, @indexTypes) = @_;
  my @beents = $self->getBackendsForSuffix($suffix, qw(cn));
  # assume 1 local backend
  my $dn = "cn=$attr,cn=index," . $beents[0]->dn;
  my $entry = new Net::LDAP::Entry();
  $entry->dn($dn);
  $entry->add('objectclass' => ['top', 'nsIndex']);
  $entry->add('cn' => $attr);
  $entry->add('nsSystemIndex' => "false");
  $entry->add('nsIndexType', \@indexTypes);
  my $mesg = $self->add($entry);
  check_mesg($mesg, "Error adding index entry $dn",
             {LDAP_ALREADY_EXISTS => LDAP_ALREADY_EXISTS});
}

sub requireIndex {
  my ($self, $suffix) = @_;
  my @beents = $self->getBackendsForSuffix($suffix, qw(cn));
  # assume 1 local backend
  my $dn = $beents[0]->dn;
  my $mesg = $self->modify($dn, replace => {'nsslapd-require-index' => 'on'});
  check_mesg($mesg, "Error making index required for $dn");
}

sub startTaskAndWait {
  my ($self, $entry, $verbose) = @_;

  my $dn = $entry->dn;
  # start the task
  my $mesg = $self->add($entry);
  check_mesg($mesg, "Error adding task entry $dn");
  $mesg = $self->search(base => $dn, scope => "base", filter => "(objectclass=*)");
  check_mesg($mesg, "Error searching for task entry $dn");
  $entry = $mesg->shift_entry;
  if (! $entry) {
	print "Entry $dn was added successfully, but I cannot search it\n" if ($verbose);
	return -1;
  } elsif ($verbose) {
	$entry->dump;
  }

  # wait for task completion - task is complete when the nsTaskExitCode attr is set
  my $attrlist = [qw(nsTaskLog nsTaskStatus nsTaskExitCode nsTaskCurrentItem nsTaskTotalItems)];
  my $done = 0;
  my $exitCode = 0;
  while (! $done) {
	sleep 1;
	$mesg = $self->search(base => $dn, scope => "base",
						  filter => "(objectclass=*)", attrs => $attrlist);
	check_mesg($mesg, "Error checking status of task $dn");
	$entry = $mesg->shift_entry;
	$entry->dump if ($verbose);
	if ($entry->exists('nsTaskExitCode')) {
	  $exitCode = $entry->get_value('nsTaskExitCode');
	  $done = 1;
	}
  }

  return $exitCode;
}

sub importLDIF {
  my ($self, $file, $suffix, $be, $verbose, $rc) = @_;
  my $cn = "import" . time;
  my $dn = "cn=$cn, cn=import, cn=tasks, cn=config";
  my $entry = new Net::LDAP::Entry();
  $entry->dn($dn);
  $entry->add('objectclass' => ['top', 'extensibleObject']);
  $entry->add('cn' => $cn);
  $entry->add('nsFilename' => $file);
  if ($be) {
	$entry->add('nsInstance' => $be);
  } else {
	$entry->add('nsIncludeSuffix' => $suffix);
  }

  $rc = $self->startTaskAndWait($entry, $verbose);

  if ($rc) {
	print "Error: import task $cn exited with $rc\n" if ($verbose);
  } else {
	print "Import task $cn completed successfully\n" if ($verbose);
  }

  return $rc;
}

sub exportLDIF {
  my ($self, $file, $suffix, $forrepl, $verbose, $rc) = @_;
  my $cn = "export" . time;
  my $dn = "cn=$cn, cn=export, cn=tasks, cn=config";
  my $entry = new Net::LDAP::Entry();
  $entry->dn($dn);
  $entry->add('objectclass' => ['top', 'extensibleObject']);
  $entry->add('cn' => $cn);
  $entry->add('nsFilename' => $file);
  $entry->add('nsIncludeSuffix' => $suffix);
  $entry->add('nsExportReplica' => "true") if ($forrepl); # create replica init file

  $rc = $self->startTaskAndWait($entry, $verbose);

  if ($rc) {
	print "Error: export task $cn exited with $rc\n" if ($verbose);
  } else {
	print "Export task $cn completed successfully\n" if ($verbose);
  }

  return $rc;
}

# use two ways: give conn and full path to archiveDir
# OR
# give conn, server root, and instance dir - a timestamp based archive name will be
# generated and returned
sub backupDB {
  my ($self, $archiveDir, $verbose, $rc) = @_;
  my $curtime = time;
  my $cn = "backup" . $curtime;
  my $dn = "cn=$cn, cn=backup, cn=tasks, cn=config";
  if (! $archiveDir) { # $archiveDir should not exist yet, so this must be the server root
	$archiveDir = "$self->{sroot}/slapd-$self->{inst}/bak/$curtime";
  } # also, this only works on the localhost
  my $entry = new Net::LDAP::Entry();
  $entry->dn($dn);
  $entry->add('objectclass' => ['top', 'extensibleObject']);
  $entry->add('cn' => $cn);
  $entry->add('nsArchiveDir' => $archiveDir);

  $rc = $self->startTaskAndWait($entry, $verbose);

  if ($rc) {
	print "Error: backup task $cn exited with $rc\n" if ($verbose);
	return 0;
  } else {
	print "Backup task $cn completed successfully\n" if ($verbose);
  }

  return $archiveDir;
}

sub restoreDB {
  my ($self, $archiveDir, $verbose, $rc) = @_;
  my $curtime = time;
  my $cn = "restore" . $curtime;
  my $dn = "cn=$cn, cn=restore, cn=tasks, cn=config";
  my $entry = new Net::LDAP::Entry();
  $entry->dn($dn);
  $entry->add('objectclass' => ['top', 'extensibleObject']);
  $entry->add('cn' => $cn);
  $entry->add('nsArchiveDir' => $archiveDir);

  $rc = $self->startTaskAndWait($entry, $verbose);

  if ($rc) {
	print "Error: restore task $cn exited with $rc\n" if ($verbose);
  } else {
	print "Restore task $cn completed successfully\n" if ($verbose);
  }

  return $rc;
}

sub serverCmd {
  my ($self, $cmd, $verbose, $timeout) = @_;
  my ($sroot, $inst) = ($self->{sroot}, $self->{inst});
  my $instanceDir = $sroot . "/slapd-" . $inst;
  my $errLog = $instanceDir . "/" . 'logs' . "/" . 'errors';
  if ($self->{errlog}) {
	$errLog = $self->{errlog};
  }
  # emulate tail -f
  # if the last line we see does not contain "slapd started", try again
  my $done = 0;
  my $started = 1;
  my $code = 0;
  my $lastLine = "";
  $cmd = lc($cmd);
  my $fullCmd = $instanceDir . "/$cmd-slapd";
  my $cmdPat = (($cmd eq 'start') ? 'slapd started\.' : 'slapd stopped\.');

  $timeout = $timeout?$timeout:120; # default is 120 seconds
  $timeout = time + $timeout;	# 20 minutes
  if ($cmd eq 'stop') {
	$self->disconnect();
  }

  open(IN, $errLog) or print "Could not open error log $errLog: $!\n", return -1;
  seek IN, 0, 2; # go to eof
  my $pos = tell(IN);
  # . . . reset the EOF status of the file desc
  seek(IN, $pos, 0);
  $code = system($fullCmd);
  while (($done == 0) && (time < $timeout)) {
    for (; ($done == 0) && ($_ = <IN>); $pos = tell(IN)) {
      $lastLine = $_;
	  print if ($verbose);
      # the server has already been started and shutdown once . . .
      if (/$cmdPat/) {
		$started++;
		if ($started == 2) {
		  $done = 1;
		}
		# sometimes the server will fail to come up; in that case, restart it
      } elsif (/Initialization Failed/) {
		#				print "Server failed to start: $_";
		$code = system($fullCmd);
		# sometimes the server will fail to come up; in that case, restart it
      } elsif (/exiting\./) {
		#				print "Server failed to start: $_";
		#$code = &mySystem($fullCmd);

		$code = system($fullCmd);
      }
    }
    if ($lastLine =~ /PR_Bind/) {
      # server port conflicts with another one, just report and punt
      print $lastLine;
      print "This server cannot be started until the other server on this\n";
      print "port is shutdown.\n";
      $done = 1;
    }
    if ($done == 0) {
      # rest a bit, then . . .
      sleep(2);
      # . . . reset the EOF status of the file desc
      seek(IN, $pos, 0);
    }
  }
  close(IN);

  if ($started < 2) {
    $! = $code;
    $now = time;
    if ($now > $timeout) {
    	print "Possible timeout: timeout=$timeout now=$now\n";
    }
    print "Error: could not $cmd server $sroot $inst: $!" if ($verbose);
	return 1;
  } else {
	print "$cmd was successful for $sroot $inst\n" if ($verbose);
	if ($cmd eq 'start') {
	  $self->init();
	}
  }

  return 0;
}

sub start {
  my ($self, $verbose, $timeout) = @_;
  if (!$self->{isLocal} && $self->{asport}) {
	my %cgiargs = ( 'dummy' => 'dummy' );
	print "starting remote server ", $self->toString(), "\n" if ($verbose);
	my $rc = &cgiPost($self->{host}, $self->{asport}, $self->{cfgdsuser},
					  $self->{cfgdspwd},
					  "/slapd-$self->{inst}/Tasks/Operation/start",
					  $verbose, \%cgiargs);
	print "connecting remote server ", $self->toString(), "\n" if ($verbose);
	$self->init() if (!$rc);
	print "started remote server ", $self->toString(), " rc = $rc\n" if ($verbose);
	return $rc;
  } else {
	return $self->serverCmd('start', $verbose, $timeout);
  }
}

sub stop {
  my ($self, $verbose, $timeout) = @_;
  if (!$self->{isLocal} && $self->{asport}) {
	print "stopping remote server ", $self->toString(), "\n" if ($verbose);
	$self->disconnect();
	print "closed remote server ", $self->toString(), "\n" if ($verbose);
	my %cgiargs = ( 'dummy' => 'dummy' );
	my $rc = &cgiPost($self->{host}, $self->{asport}, $self->{cfgdsuser},
					  $self->{cfgdspwd},
					  "/slapd-$self->{inst}/Tasks/Operation/stop",
					  $verbose, \%cgiargs);
	print "stopped remote server ", $self->toString(), " rc = $rc\n" if ($verbose);
	return $rc;
  } else {
	return $self->serverCmd('stop', $verbose, $timeout);
  }
}

sub addSchema {
  my ($self, $attr, $val) = @_;
  my $dn = "cn=schema";
  my $mesg = $self->modify($dn, add => {$attr => $val});
  check_mesg($mesg, "Could not add $attr $val to schema");
  return 0;
}

sub addAttr {
  my $self = shift;
  return $self->addSchema('attributeTypes', @_);
}

sub addObjClass {
  my $self = shift;
  return $self->addSchema('objectClasses', @_);
}

sub waitForEntry {
  my ($self, $dn, $timeout, $attr, $quiet, $rc) = @_;
  my $scope = "base";
  my $filter = "(objectclass=*)";
  if ($attr) {
	$filter = "($attr=*)";
  }
  my @attrlist = ();
  if ($attr) {
	@attrlist = ($attr);
  }
  $timeout = ($timeout ? $timeout : 7200);
  $timeout = time + $timeout;

  if (ref($dn) eq 'Net::LDAP::Entry') {
	$dn = $dn->dn;
  }
  # wait for entry and/or attr to show up
  my $mesg = $self->search(base => $dn, scope => $scope, filter => $filter, attrs => [@attrlist]);
  check_mesg($mesg, "Error waiting for entry $dn",
			 {LDAP_NO_SUCH_OBJECT => LDAP_NO_SUCH_OBJECT});
  $rc = $mesg->code();
  $attr = "" if (!$attr); # to avoid uninit. variable
  $| = 1; #keep that output coming...
  print "Waiting for $dn:$attr ", $self->toString() if (!$quiet);
  my $entry = $mesg->shift_entry();
  while (!$entry && (time < $timeout)) {
	print "$rc:" if (!$quiet);
	sleep 1;
	my $mesg = $self->search(base => $dn, scope => $scope, filter => $filter, attrs => [@attrlist]);
	check_mesg($mesg, "Error waiting for entry $dn",
			   {LDAP_NO_SUCH_OBJECT => LDAP_NO_SUCH_OBJECT});
	$entry = $mesg->shift_entry;
	$rc = $mesg->code;
  }
  if (!$entry && (time > $timeout)) {
	print "\nwaitForEntry timeout for $dn for ", $self->toString(), "\n";
  } elsif ($entry && !$quiet) {
	print "\nThe waited for entry is:\n";
	$entry->dump;
	print "\n";
  } elsif (!$entry) {
	print "\nwaitForEntry error $rc reading $dn for ", $self->toString(), "\n";
  }
  return $entry;
}

# if $parentOrEntry is a string DN, add a random entry using that DN as the parent
# if $parentOrEntry is an Entry, add the entry
# returns the entry added or undef
sub addEntry {
  my ($self, $parentOrEntry, $check) = @_;
  my $rc;
  my $dn;
  my $entry;
  if (ref($parentOrEntry) ne 'Net::LDAP::Entry') {
	my $cn = "repl" . rand(100);
	$dn = "cn=$cn, " . $parentOrEntry;
	$mesg = $self->search(base => $dn, scope => "base", filter => "(objectclass=*)");
	check_mesg($mesg, "Error searching for $dn",
			   {LDAP_NO_SUCH_OBJECT => LDAP_NO_SUCH_OBJECT});
	$entry = $mesg->shift_entry;
	if (!$entry) {
	  $entry = new Net::LDAP::Entry;
	  $entry->dn($dn);
	  $entry->add('objectclass' => ["top", "extensibleobject"]);
	  $entry->add('cn', $cn);
	  $mesg = $self->add($entry);
	}
  } else {
	$entry = $parentOrEntry;
	$dn = $entry->dn;
	$mesg = $self->add($entry);
  }
  check_mesg($mesg, "Could not add entry $dn");
  if ($check) {
	$mesg = $self->search(base => $dn, scope => "base", filter => "(objectclass=*)");
	check_mesg($mesg, "Could not search for new entry $dn");
	$entry = $mesg->shift_entry;
	$entry->dump;
  }
  return $entry;
}

sub enableReplLogging {
  my $self = shift;
  return $self->setLogLevel(8192);
}

sub disableReplLogging {
  my $self = shift;
  return $self->setLogLevel(0);
}

sub setLogLevel {
  my ($self, @vals) = @_;
  my ($rc, %mod, $val);
  for (@vals) {
	$val += $_;
  }
  my $mesg = $self->modify('cn=config', replace => {'nsslapd-errorlog-level' => $val});
  check_mesg($mesg, "Could not set log level to $val");

  return $rc;
}

sub setAccessLogLevel {
  my ($self, @vals) = @_;
  my ($rc, %mod, $val);
  for (@vals) {
	$val += $_;
  }
  my $mesg = $self->modify('cn=config', replace => {'nsslapd-accesslog-level' => $val});
  check_mesg($mesg, "Could not set access log level to $val");

  return $rc;
}

sub setDBReadOnly {
  my ($self, $val, $bename) = @_;
  $bename = ($bename ? $bename : "userRoot");
  my $dn = "cn=$bename, cn=ldbm database, cn=plugins, cn=config";
  my $mesg = $self->modify($dn, replace => {'nsslapd-readonly' => $val});
  check_mesg($mesg, "Could not set nsslapd-readonly to $val");

  return $rc;
}

# argument is a hashref - key is password policy attr, value is off or on
# attrs are: 
#	passwordchecksyntax    - check password syntax when adding/changing password
#	passwordexp            - check for password expiration
#	passwordhistory        - keep and check password history
#	passwordlockout        - lockout accounts after unsuccessful bind attempts
#	passwordisglobalpolicy - allow replication of operational password policy attrs in user entries
sub setupPasswordPolicy {
  my ($self, $href) = @_;
  my @changes;
  while (my ($key, $val) = each %{$href}) {
	push @changes, ( replace => [ $key => $val ] );
	print "setupPasswordPolicy: $key is $val\n";
  }
  my $mesg = $self->modify("cn=config", changes => \@changes);
  check_mesg($mesg, "Could not setup password policy");
  return 0;
}

sub setupChainingIntermediate {
  my ($self, $bename) = @_;

  my $confdn = "cn=config,cn=chaining database,cn=plugins,cn=config";
  my $mesg = $self->modify($confdn, add =>
						   {nsTransmittedControl =>
								[ '2.16.840.1.113730.3.4.12', '1.3.6.1.4.1.1466.29539.12' ]
						   }
						  );
  check_mesg($mesg, "Could not setup chaining intermediate",
			 {LDAP_TYPE_OR_VALUE_EXISTS => LDAP_TYPE_OR_VALUE_EXISTS});

  return 0;
}

sub setupChainingMux {
  my ($self, $suffix, $isIntermediate, $binddn, $bindpw, @urls) = @_;
  my $rc = $self->addSuffix($suffix, $binddn, $bindpw, @urls);
  if (!$rc && $isIntermediate) {
	$rc = $self->setupChainingIntermediate($suffix);
  }
  return $rc;
}

sub setupChainingFarm {
  my ($self, $suffix, $binddn, $bindcn, $bindpw) = @_;
  my $rc;
  # step 1 - create the bind dn to use as the proxy
  if ($rc = $self->setupBindDN($binddn, $bindcn, $bindpw)) {
	print "Couldn't setup chaining bind dn $binddn $rc: " . $self->getErrorString(), "\n";
  } elsif ($rc = $self->addSuffix($suffix)) { # step 2 - create the suffix
	print "Couldn't add chaining suffix $bename $suffix $rc: " . $self->getErrorString(), "\n";
  } else {
	# step 3 - add the proxy ACI to the suffix
    my $mesg = $self->modify($suffix, add =>
							 {aci =>
								  [ "(targetattr = \"*\")(version 3.0; acl \"Proxied authorization for database links\"; allow (proxy) userdn = \"ldap:///$binddn\";)" ]
							  }
							 );
	check_mesg($mesg, "Could not add aci for chaining farm",
			   {LDAP_TYPE_OR_VALUE_EXISTS => LDAP_TYPE_OR_VALUE_EXISTS});
  }

  return $rc;
}

# setup chaining from self to $to - self is the mux, to is the farm
# if isIntermediate is set, this server will chain requests from another server to $to
sub setupChaining {
  my ($self, $to, $suffix, $isIntermediate) = @_;
  my $bindcn = "chaining user";
  my $binddn = "cn=$bindcn,cn=config";
  my $bindpw = "chaining";

  $to->setupChainingFarm($suffix, $binddn, $bindcn, $bindpw);
  $self->setupChainingMux($suffix, $isIntermediate, $binddn, $bindpw, $to->toLDAPURL());
}

sub setupChangelog {
  my ($self, $dir) = @_;
  my $dn = "cn=changelog5, cn=config";
  my $mesg = $self->search(base => $dn, scope => "base", filter => "(objectclass=*)");
  check_mesg($mesg, "Error searching for changelog $dn",
			 {LDAP_NO_SUCH_OBJECT => LDAP_NO_SUCH_OBJECT});
  my $entry = $mesg->shift_entry;
  return 0 if ($entry);
  $dir = $dir ? $dir : "$self->{sroot}/slapd-$self->{inst}/../slapd-$self->{inst}/cldb";
  $entry = new Net::LDAP::Entry();
  $entry->dn($dn);
  $entry->add('objectclass' => ["top", "extensibleobject"]);
  $entry->add('cn' => "changelog5");
  $entry->add('nsslapd-changelogdir' => $dir);
  $mesg = $self->add($entry);
  check_mesg($mesg, "Could not add the changelog config entry $dn");
  $mesg = $self->search(base => $dn, scope => "base", filter => "(objectclass=*)");
  check_mesg($mesg, "Could not get the newly added changelog config entry $dn");
  $entry = $mesg->shift_entry;
  if (! $entry) {
	print "Entry $dn was added successfully, but I cannot search it\n";
	return -1;
  } else {
	$entry->dump;
  }
  return 0;
}

sub enableChainOnUpdate {
  my ($self, $suffix, $bename) = @_;
  # first, get the mapping tree entry to modify
  my $mtent = $self->getMTEntry($suffix, qw(cn));
  my $dn = $mtent->dn();

  # next, get the path of the replication plugin
  my $mesg = $self->search(base => "cn=Multimaster Replication Plugin,cn=plugins,cn=config",
						   scope => "base", filter => "(objectclass=*)",
						   attrs => [ 'nsslapd-pluginPath' ]);
  check_mesg($mesg, "Could not find the repl plugin entry");
  my $plgent = $mesg->shift_entry;
  my $path = $plgent->get_value('nsslapd-pluginPath');

  my @changes = ( [replace => [ 'nsslapd-state' => 'backend' ] ],
				  [add     => [ 'nsslapd-backend' => $bename ] ],
				  [add     => [ 'nsslapd-distribution-plugin' => $path ] ],
				  [add     => [ 'nsslapd-distribution-funct'  => 'repl_chain_on_update'] ]
				);
  $mesg = $self->modify($dn, \@changes);
  check_mesg($mesg, "Could not set up repl_chain_on_update",
			 {LDAP_TYPE_OR_VALUE_EXISTS => LDAP_TYPE_OR_VALUE_EXISTS});
  return 0;
}

sub setupConsumerChainOnUpdate {
  my ($self, $suffix, $isIntermediate, $binddn, $bindpw, @urls) = @_;
  # suffix should already exist
  # we need to create a chaining backend
  my $chainbe = $self->setupBackend($suffix, $binddn, $bindpw, \@urls,
								   { 'nsCheckLocalACI'            => 'on' }); # enable local db aci eval.
  # do the stuff for intermediate chains
  $self->setupChainingIntermediate($chainbe) if ($isIntermediate);
  # enable the chain on update
  return $self->enableChainOnUpdate($suffix, $chainbe);
}

my $REPLICAID = 0;
my $MASTER_TYPE = 0;
# N = 1 - a hub (read only supplier)
my $HUB_TYPE = 1;
# N = 2 - a "leaf" consumer
my $LEAF_TYPE = 2;

# arguments to set up a replica:
# suffix - dn of suffix
# type - master, hub, leaf (see above for values) - if type is omitted, default is master
# legacy - true or false for legacy consumer
# id - replica id
# binddn - the replication bind dn for this replica
# if replica ID is not given, an internal sequence number will be assigned
# call like this:
# $thing->setupReplica({
#		suffix => "dc=example, dc=com",
#		type => $MASTER_TYPE,
#		binddn => "cn=replication manager, cn=config",
#		id => 3
#  });
# binddn can also be an array ref:
#	binddn => [ "cn=repl1, cn=config", "cn=repl2, cn=config" ],
sub setupReplica {
  my ($self, $args) = @_;
  my $rc;
  my $suffix = $args->{suffix};
  my $type = $args->{type} || $MASTER_TYPE;
  my $legacy = $args->{legacy};
  my $binddn = $args->{binddn};
  my $id = $args->{id};
  my $tpi = $args->{tombstone_purge_interval};
  my $pd = $args->{purge_delay};
  my $referrals = $args->{referrals};
  my $nsuffix = normalizeDN($suffix);
  my $dn = "cn=replica, cn=\"" . $nsuffix . "\", cn=mapping tree, cn=config";

  my $mesg = $self->search(base => $dn, scope => "base", filter => "(objectclass=*)");
  check_mesg($mesg, "Could not find the replica entry for $suffix",
			 {LDAP_NO_SUCH_OBJECT => LDAP_NO_SUCH_OBJECT});
  if (my $entry = $mesg->shift_entry) {
	$self->{$nsuffix}{dn} = $dn;
	return 0;
  }

  my @binddnlist;
  if ($binddn && ref($binddn)) {
	@binddnlist = @{$binddn};
  } elsif ($binddn) {
	push @binddnlist, $binddn;
  } else {
	push @binddnlist, $REPLBINDDN;
  }

  if (!$id && !$type) {
	$id = ++$REPLICAID;
  } elsif (!$id) {
	$id = 0;
  } else {
	# replica id was given, so use that for our internal counter
	$REPLICAID = $id;
	die;
  }

  $entry = new Net::LDAP::Entry();
  $entry->dn($dn);
  $entry->add('objectclass' => ["top", "nsds5replica", "extensibleobject"]);
  $entry->add('cn' => "replica");
  $entry->add('nsds5replicaroot' => $nsuffix);
  $entry->add('nsds5replicaid' => $id);
  $entry->add('nsds5replicatype' => ($type ? "2" : "3"));
  $entry->add('nsds5flags' => "1") if ($type != $LEAF_TYPE);
  $entry->add('nsds5replicabinddn' => \@binddnlist);
  $entry->add('nsds5replicalegacyconsumer' => ($legacy ? "on" : "off"));
  $entry->add('nsds5replicatombstonepurgeinterval' => $tpi) if ($tpi);
  $entry->add('nsds5ReplicaPurgeDelay' => $pd) if ($pd);
  $entry->add('nsds5ReplicaReferral' => $referrals) if ($referrals);
  $entry->add('nsds5ReplicaReferral' => $referrals) if ($referrals);
  $mesg = $self->add($entry);
  check_mesg($mesg, "Could not add replica entry $dn");
  $mesg = $self->search(base => $dn, scope => "base", filter => "(objectclass=*)");
  check_mesg($mesg, "Could not find the new replica entry $dn");
  $entry = $mesg->shift_entry;
  if (! $entry) {
	  print "Entry $dn was added successfully, but I cannot search it\n";
	  return -1;
  } else {
	  $entry->replace(nsState => []);
	  $entry->replace(nsstate => []);
	  $entry->dump;
  }
  $self->{$nsuffix}{dn} = $dn;
  $self->{$nsuffix}{type} = $type;
  return $rc;
}

sub setupLegacyConsumer {
  my ($self, $binddn, $bindpw, $rc) = @_;
  my $legacydn = "cn=legacy consumer, cn=replication, cn=config";
  my $mesg = $self->search(base => $legacydn, scope => "base", filter => "(objectclass=*)");
  check_mesg($mesg, "Could not search legacy dn $legacydn",
			 {LDAP_NO_SUCH_OBJECT => LDAP_NO_SUCH_OBJECT});
  my $entry = $mesg->shift_entry;
  if (! $entry) {
#  $self->delete($entry) if ($entry);
	$entry = new Net::LDAP::Entry();
	$entry->dn($legacydn);
	$entry->add('objectclass' => ["top", "extensibleObject"]);
	$entry->add('nsslapd-legacy-updatedn' => $binddn ? $binddn : $REPLBINDDN);
	$entry->add('nsslapd-legacy-updatepw' => $bindpw ? $bindpw : $REPLBINDPW);
	$mesg = $self->add($entry);
	check_mesg($mesg, "Could not add legacy dn $legacydn");
	$mesg = $self->search(base => $legacydn, scope => "base", filter => "(objectclass=*)");
	check_mesg($mesg, "Could not search legacy dn $legacydn");
	$entry = $mesg->shift_entry;
	if (! $entry) {
		print "Entry $legacydn was added successfully, but I cannot search it: " . $self->getErrorString(),
		"\n";
		return -1;
	} else {
		$entry->dump;
	}
  }
  return 0;
}

# $dn can be an entry
sub setupBindDN {
  my ($self, $dn, $cn, $pwd, $rc) = @_;
  my $ent;
  if ($dn && (ref($dn) eq 'Net::LDAP::Entry')) {
	$ent = $dn;
	$dn = $ent->dn();
  } elsif (!$dn) {
	$dn = $REPLBINDDN;
  }
  my $mesg = $self->search(base => $dn, scope => "base", filter => "(objectclass=*)");
  check_mesg($mesg, "Could not search $dn", {LDAP_NO_SUCH_OBJECT => LDAP_NO_SUCH_OBJECT});
  my $entry = $mesg->shift_entry;
  return 0 if ($entry);
  if (!$ent) {
	$ent = new Net::LDAP::Entry();
	$ent->dn($dn);
	$ent->add('objectclass' => ["top", "person"]);
	$ent->add('cn' => $cn ? $cn : $REPLBINDCN);
	$ent->add('userpassword' => $pwd ? $pwd : $REPLBINDPW);
	$ent->add('sn' => "bind dn pseudo user");
  }
  $mesg = $self->add($ent);
  check_mesg($mesg, "Could not add bind dn $dn");
  $mesg = $self->search(base => $dn, scope => "base", filter => "(objectclass=*)");
  check_mesg($mesg, "Could not find new dn $dn");
  $ent = $mesg->shift_entry;
  if (! $ent) {
	  print "Entry $dn was added successfully, but I cannot search it\n";
	  return -1;
  } else {
	  $ent->dump;
  }

  return 0;
}

sub setupReplBindDN {
  my ($self, $dn, $cn, $pwd, $rc) = @_;
  return $self->setupBindDN($dn, $cn, $pwd);
}

# args - NDSAdminNL consumer, suffix, binddn, bindpw, timeout
sub setupAgreement {
  my ($self, $repoth, $suffix, $binddn, $bindpw, $chain, $timeout, $fractional, $rc) = @_;
  my $nsuffix = normalizeDN($suffix);
  my ($othhost, $othport, $othsslport) =
	($repoth->{host}, $repoth->{port}, $repoth->{sslport});
  $othport = ($othsslport ? $othsslport : $othport);
  my $dn = "cn=meTo${othhost}$othport, " . $self->{$nsuffix}{dn};
  my $mesg = $self->search(base => $dn, scope => "base", filter => "(objectclass=*)");
  check_mesg($mesg, "Could not search for repl agreement $dn",
			 {LDAP_NO_SUCH_OBJECT => LDAP_NO_SUCH_OBJECT});
  my $entry = $mesg->shift_entry;
  if ($entry) {
	print "Agreement exists:\n";
	$entry->dump;
	$self->{$nsuffix}{$repoth->toString()} = $dn;
	return $dn;
  }
#	$conn->delete($dn);
#	sleep 1;
#	$entry = $conn->search($dn, "base", "(objectclass=*)");
#	if ($entry || (($rc = $conn->getErrorCode()) != 32)) {
#	  print "Error: could not delete $dn: $rc\n";
#	}
#  }

  $entry = new Net::LDAP::Entry();
  $entry->dn($dn);
  $entry->add('objectclass' => ["top", "nsds5replicationagreement"]);
  $entry->add('cn' => "meTo${othhost}$othport");
  $entry->add('nsds5replicahost' => $othhost);
  $entry->add('nsds5replicaport' => $othport);
  $entry->add('nsds5replicatimeout' => $timeout ? $timeout : '120');
  $entry->add('nsds5replicabinddn' => $binddn ? $binddn : $REPLBINDDN);
  $entry->add('nsds5replicacredentials' => $bindpw ? $bindpw : $REPLBINDPW);
  $entry->add('nsds5replicabindmethod' => 'simple');
  $entry->add('nsds5replicaroot' => $nsuffix);
  $entry->add('nsds5replicaupdateschedule' => '0000-2359 0123456');
  $entry->add('description' => "me to ${othhost}$othport");
  $entry->add('nsds5replicatransportinfo' => 'SSL') if ($othsslport);
  $entry->add('nsDS5ReplicatedAttributeList' => $fractional) if ($fractional);
  $mesg = $self->add($entry);
  check_mesg($mesg, "Could not add repl agreement entry $dn");
  $entry = $self->waitForEntry($dn);
  if ($entry) {
	$self->{$nsuffix}{$repoth->toString()} = $dn;
	if (!$self->{$nsuffix}{type} && $chain) { # a master
	  $self->setupChainingFarm($suffix, $binddn, 0, $bindpw);
	}
	if ($repoth->{$nsuffix}{type} == $LEAF_TYPE && $chain) {
	  $repoth->setupConsumerChainOnUpdate($suffix, 0, $binddn, $bindpw, $self->toLDAPURL());
	} elsif ($repoth->{$nsuffix}{type} == $HUB_TYPE && $chain) {
	  $repoth->setupConsumerChainOnUpdate($suffix, 1, $binddn, $bindpw, $self->toLDAPURL());
	}
  }

  return $dn;
}

sub stopReplication {
  my ($self, $agmtdn, $rc) = @_;
  my %mod = ( nsds5replicaupdateschedule => { r => [ '2358-2359 0' ] });
  my $mesg = $self->modify($agmtdn, replace => {nsds5replicaupdateschedule => [ '2358-2359 0' ]});
  check_mesg($mesg, "Could not stop replication");
  return 0;
}

sub findAgreementDNs {
  my ($self, $filt, @attrs, $rc) = @_;
  my $realfilt;
  if ($filt) {
	$realfilt = "(&(objectclass=nsds5ReplicationAgreement)$filt)";
  } else {
	$realfilt = "(objectclass=nsds5ReplicationAgreement)";
  }
  @attrs = qw(cn) if (! @attrs);
  my @retdns;
  my $mesg = $self->search(base   => "cn=mapping tree,cn=config",
						   scope  => "sub",
						   filter => $realfilt,
						   attrs  => \@attrs);
  check_mesg($mesg, "Could not find any repl agreements");
  while ($ent = $mesg->shift_entry) {
	push @retdns, $ent->dn();
  }
  return @retdns;
}

sub getReplStatus {
  my ($self, $agmtdn, $rc) = @_;
  my @attrlist = qw(cn nsds5BeginReplicaRefresh nsds5replicaUpdateInProgress
					nsds5ReplicaLastInitStatus nsds5ReplicaLastInitStart
				    nsds5ReplicaLastInitEnd nsds5replicaReapActive
				    nsds5replicaLastUpdateStart nsds5replicaLastUpdateEnd
				    nsds5replicaChangesSentSinceStartup nsds5replicaLastUpdateStatus
				    nsds5replicaChangesSkippedSinceStartup nsds5ReplicaHost
				    nsds5ReplicaPort);
  my $mesg = $self->search(base => $agmtdn, scope => "base",
						   filter => "(objectclass=*)", attrs => \@attrlist);
  check_mesg($mesg, "Could not read repl status from $agmtdn");
  my $entry = $mesg->shift_entry;
  if (! $entry) {
	print "Error reading status from agreement $agmtdn\n";
  } else {
	my $cn = $entry->get_value("cn");
	my $rh = $entry->get_value("nsds5ReplicaHost");
	my $rp = $entry->get_value("nsds5ReplicaPort");
	my $retstr = "Status for " . $self->toString() . " agmt $cn:$rh:$rp\n";
	$retstr .= "\tUpdate In Progress  : " . $entry->get_value("nsds5replicaUpdateInProgress") . "\n";
	$retstr .= "\tLast Update Start   : " . $entry->get_value("nsds5replicaLastUpdateStart") . "\n";
	$retstr .= "\tLast Update End     : " . $entry->get_value("nsds5replicaLastUpdateEnd") . "\n";
	$retstr .= "\tNum. Changes Sent   : " . $entry->get_value("nsds5replicaChangesSentSinceStartup") . "\n";
	$retstr .= "\tNum. Changes Skipped: " . $entry->get_value("nsds5replicaChangesSkippedSinceStartup") . "\n";
	$retstr .= "\tLast Update Status  : " . $entry->get_value("nsds5replicaLastUpdateStatus") . "\n";
	$retstr .= "\tInit in Progress    : " . $entry->get_value("nsds5BeginReplicaRefresh") . "\n";
	$retstr .= "\tLast Init Start     : " . $entry->get_value("nsds5ReplicaLastInitStart") . "\n";
	$retstr .= "\tLast Init End       : " . $entry->get_value("nsds5ReplicaLastInitEnd") . "\n";
	$retstr .= "\tLast Init Status    : " . $entry->get_value("nsds5ReplicaLastInitStatus") . "\n";
	$retstr .= "\tReap In Progress    : " . $entry->get_value("nsds5replicaReapActive") . "\n";
	return $retstr;
  }

  return "";
}

sub restartReplication {
  my ($self, $agmtdn, $rc) = @_;
  my $mesg = $self->modify($agmtdn, replace => {nsds5replicaupdateschedule => [ '0000-2359 0123456' ]});
  check_mesg($mesg, "Could not restart replication for $agmtdn");
  return 0;
}

sub startReplication_async {
  my ($self, $agmtdn, $rc) = @_;
  my $mesg = $self->modify($agmtdn, add => {nsds5BeginReplicaRefresh => 'start'});
  check_mesg($mesg, "Could not start replication for $agmtdn");
  return $rc;
}

# returns an array - first element is done/not done, 2nd is no error/has error
sub checkReplInit {
  my ($self, $agmtdn, $rc) = @_;
  my $done = 0;
  my $haserror = 0;
  my @attrlist = qw(nsds5BeginReplicaRefresh nsds5replicaUpdateInProgress
					nsds5ReplicaLastInitStatus nsds5ReplicaLastInitStart
				    nsds5ReplicaLastInitEnd);
  my $mesg = $self->search(base => $agmtdn, scope => "base",
						   filter => "(objectclass=*)", attrs => \@attrlist);
  check_mesg($mesg, "Could not read repl init status from $agmtdn");
  my $entry = $mesg->shift_entry;
  print "\n##################################################################\n";
  $entry->dump;
  print "##################################################################\n";
  if (! $entry ) {
	print "Error reading status from agreement $agmtdn\n";
	$haserror = -1;
  } else {
	my $refresh = $entry->get_value("nsds5BeginReplicaRefresh");
	my $inprogress = $entry->get_value("nsds5replicaUpdateInProgress");
	my $status = $entry->get_value("nsds5ReplicaLastInitStatus");
	my $start = $entry->get_value("nsds5ReplicaLastInitStart");
	my $end = $entry->get_value("nsds5ReplicaLastInitEnd");
	if (! $refresh) { # done with operation, check status
	  if ($status =~ /replica busy/) {
		print "Update failed - replica busy - status $status\n";
		$done = 1;
		$haserror = 2;
	  } elsif ($status =~ /Total update succeeded/) {
		print "Update succeeded: status $status\n";
		$done = 1;
	  } elsif (lc($inprogress) eq 'true') {
		print "Update in progress yet not in progress: status $status\n";
	  } else {
		print "Update failed: status $status\n";
		$haserror = 1;
	  }
	} else {
	  print "Update in progress: status $status\n";
	}
  }

  return ($done, $haserror);
}

sub waitForReplInit {
  my ($self, $agmtdn) = @_;
  my $done = 0;
  my $haserror = 0;
  while (! $done && ! $haserror) {
	sleep 1;  # give it a few seconds to get going
	($done, $haserror) = $self->checkReplInit($agmtdn);
  }

  return $haserror;
}

sub startReplication {
  my ($self, $agmtdn) = @_;
  my $rc = $self->startReplication_async($agmtdn);
  if (!$rc) {
	$rc = $self->waitForReplInit($agmtdn);
	if ($rc == 2) { # replica busy - retry
	  $rc = $self->startReplication($agmtdn);
	}
  }

  return $rc;
}

# returns a hash ref
# ruv->{gen} is the generation
# ruv->{1} through ruv->{N} are hash refs - the number (1-N) is the replica ID
#   ->{url} is the purl
#   ->{min} is the min csn
#   ->{max} is the max csn
#   ->{lastmod} is the last modified timestamp
# example ruv attr:
# nsds50ruv: {replicageneration} 3b0ebc7f000000010000
# nsds50ruv: {replica 1 ldap://myhost:51010} 3b0ebc9f000000010000 3b0ebef700000
#  0010000
# nsruvReplicaLastModified: {replica 1 ldap://myhost:51010} 292398402093
# if the tryrepl flag is true, if getting the ruv from the suffix fails, try getting
# the ruv from the cn=replica entry
sub getRUV {
  my ($self, $suffix, $tryrepl, $verbose, $rc) = @_;
  my $uuid = "ffffffff-ffffffff-ffffffff-ffffffff";
  my $mesg = $self->search(base   => $suffix,
						   scope  => "one",
						   filter => "(&(nsuniqueid=$uuid)(objectclass=nsTombstone))",
						   attrs  => [ 'nsds50ruv', 'nsruvReplicaLastModified']);
  check_mesg($mesg, "Could not read tombstone entry for $suffix",
			 {LDAP_NO_SUCH_OBJECT => LDAP_NO_SUCH_OBJECT});
  my $entry = $mesg->shift_entry;
  if (!$entry || !$entry->get_value("nsds50ruv")) {
	print "Error: could not get ruv from $self->{host}:$self->{port} for $suffix: \n" if ($verbose);
	if ($tryrepl) {
	  $mesg = $self->search(base   => "cn=replica,cn=\"$suffix\",cn=mapping tree,cn=config",
							scope  => "base",
							filter => "(objectclass=*)",
							attrs => ['nsds50ruv']);
	  check_mesg($mesg, "Could not read cn=replica tombstone entry for $suffix",
				 {LDAP_NO_SUCH_OBJECT => LDAP_NO_SUCH_OBJECT});
	  $entry = $mesg->shift_entry;
	  if (!$entry || !$entry->get_value("nsds50ruv")) {
		print "Error: could not get cn=replica ruv from $self->{host}:$self->{port} for $suffix: ",
		      "\n" if ($verbose);
		return 0;
	  }
	} else {
	  return 0;
	}
  }
  my $ruv = {};
  for ($entry->get_value("nsds50ruv")) {
	if (/\{replicageneration\}\s+(\w+)/) {
	  $ruv->{gen} = $1;
	} elsif (/\{replica\s+(\d+)\s+(.+?)\}\s*(\w*)\s*(\w*)/) {
	  $ruv->{$1}->{url} = $2;
	  $ruv->{$1}->{min} = $3;
	  $ruv->{$1}->{max} = $4;
	} else {
	  print "unknown ruv element: $_\n";
	}
  }
  for ($entry->get_value("nsruvReplicaLastModified")) {
	if (/\{replica\s+(\d+)\s+(.+?)\}\s*(\w*)/) {
	  $ruv->{$1}->{lastmod} = hex($3); # convert to integer
	} else {
	  print "unknown ruv lastmod element: $_\n";
	}
  }
  return $ruv;
}

sub printRUV {
  my $ruv = shift;
  if (!$ruv) {
	print "ruv is NULL\n";
	return;
  }
  print "gen ", $ruv->{gen}, "\n";
  foreach my $ii ( keys %$ruv ) {
	next if ( $ii eq "gen" );
	print "  $ii ", $ruv->{$ii}->{url}, " ",
	  $ruv->{$ii}->{min}, " ", $ruv->{$ii}->{max}, " ",
	  $ruv->{$ii}->{lastmod}, "\n";
  }
}

# takes a CSN string and returns an array of ts, seq, rid, subseq
sub parseCSN {
  my $str = shift;
  my @csn;
  if ($str =~ /(.{8})(.{4})(.{4})(.{4})/) {
	@csn = (hex($1), hex($2), hex($3), hex($4));
  }

  return @csn;
}

# takes an array of hexadecimal string and returns an array of refs to arrays of 4 integers
sub parseCSNs {
  my @ret;
  for (@_) {
	# if someone knows how to do this with unpack, please do!
	my @csn = parseCSN($_);
	push @ret, \@csn;
  }

  return @ret;
}

sub getTSDiff {
 my ($ts1, $ts2) = @_;
 my $diff = $ts1 - $ts2;
 my $diffstr = "plus ";
 if ($diff < 0) {
   $diff = 0 - $diff;
   $diffstr = "minus ";
 }
 if (!$diff) {
   return "no difference ";
 }

 # diff is in seconds - lets format as weeks, days, etc.
 my $oneminute = 60;
 my $onehour = $oneminute * 60;
 my $oneday = $onehour * 24;
 my $oneweek = $oneday * 7;

 my $n = int($diff / $oneweek);
 $diffstr .= "$n wk " if ($n);
 $diff -= $n*$oneweek;

 $n = int($diff / $oneday);
 $diffstr .= "$n dy " if ($n);
 $diff -= $n*$oneday;

 $n = int($diff / $onehour);
 $diffstr .= "$n hr " if ($n);
 $diff -= $n*$onehour;

 $n = int($diff / $oneminute);
 $diffstr .= "$n min " if ($n);
 $diff -= $n*$oneminute;

 $diffstr .= "$diff sec " if ($diff);

 return $diffstr;
}

sub printTSDiff {
  print &getTSDiff(@_), "\n";
} 

sub printTS {
  for (@_) {
	print scalar(localtime($_)), "\n";
  }
}

sub compareCSNs {
  my ($csn1, $csn2) = @_;
  return 1 if (!$csn1 && !$csn2); # both null, so equal
  if (!$csn1) { print "csn1 is NULL\n"; return 0; }
  if (!$csn2) { print "csn2 is NULL\n"; return 0; }

  my @ary = &parseCSNs(@_);
  my $equal = 1;

  my $tsdiff = $ary[0]->[0] - $ary[1]->[0];
  printTSDiff($ary[0]->[0], $ary[1]->[0]) if ($tsdiff);
  $equal = 0 if ($tsdiff);

  my $seqdiff = $ary[0]->[1] - $ary[1]->[1];
  print "seq diff $seqdiff\n" if ($seqdiff);
  $equal = 0 if ($seqdiff);

  my $riddiff = $ary[0]->[2] - $ary[1]->[2];
  print "rid diff $riddiff\n" if ($riddiff);
  $equal = 0 if ($riddiff);

  my $subseqdiff = $ary[0]->[3] - $ary[1]->[3];
  print "subseq diff $subseqdiff\n" if ($subseqdiff);
  $equal = 0 if ($subseqdiff);

  return $equal;
}

# returns
# 1 if ruvs are equal
# 0 otherwise
sub compareRUVs {
  my ($ruv1, $ruv2) = @_;
  return 1 if ($ruv1 == $ruv2);
  return 0 if (!$ruv1 || !$ruv2);
  my $ret = &compareCSNs($ruv1->{gen}, $ruv2->{gen});
  print "replica generation differs\n" unless($ret);
  for (my $ii = 1; $ruv1->{$ii}; ++$ii) {
	my $el1 = $ruv1->{$ii};
	my $el2 = $ruv2->{$ii};
	print "mincsns differ\n" unless ($ret = &compareCSNs($el1->{min}, $el2->{min}));
	print "maxcsns differ\n" unless ($ret = &compareCSNs($el1->{max}, $el2->{max}));
  }

  return $ret;
}

sub getCgiContentAndLength {
  my $args = shift;
  my $escapechars = "^a-zA-Z0-9"; # escape all non alphanum chars
  my $content = "";
  my $firsttime = 1;
  while (my ($kk, $vv) = each %{$args}) {
	if ($firsttime) {
	  $firsttime = 0;
	} else {
	  $content = $content . "&";
	}
	$content = $content . $kk . "=" . uri_escape($vv, $escapechars);
  }
  my $length = length($content);

  return ($content, $length);
}

# fakes out the ds_create program into thinking it is getting cgi input
sub cgiFake {
  my ($sroot, $verbose, $prog, $args) = @_;
  # construct content string
  my ($content, $length) = &getCgiContentAndLength($args);

  # setup CGI environment
  $ENV{REQUEST_METHOD} = "POST";
  $ENV{NETSITE_ROOT} = $sroot;
  $ENV{CONTENT_LENGTH} = $length;

#  print "content = $content\n";

  # open the program
  my $curdir = getcwd();
  my $dir = dirname($prog);
  my $exe = basename($prog);
  chdir $dir;
  my $input = gensym();
  my $output = gensym();
  my $pid = open2($input, $output, "./$exe");
  sleep(1); # allow prog to init stdin read buffers
  print $output $content, "\n";
  CORE::close $output;

  if ($?) {
	print "Warning: $prog returned code $? and $!\n";
  }

  my $exitCode = 1;
  my @lines;
  while (<$input>) {
	print $_ if ($verbose);
	push @lines, $_;
	if (/^NMC_Status:\s*(\d+)/) {
	  $exitCode = $1;
	  last;
	}
  }
  CORE::close $input;
  chdir $curdir;

  if ($exitCode) {
	print "CGI $prog failed with $exitCode: here is the output:\n";
	map { print $_ } @lines;
  }

  if ($exitCode != 0) {
	print "Error: could not run $prog: $exitCode\n";
	return $exitCode;
  }

  return 0;
}

sub cgiPost {
  my ($host, $port, $user, $pwd, $url, $verbose, $args) = @_;
  # construct auth string
  my $auth = encode_base64($user . ":" . $pwd);
  $auth =~ s/\n//g;
  # construct content string
  my ($content, $length) = &getCgiContentAndLength($args);

  # construct header
  my $header =
"POST $url HTTP/1.0\n" .
"Host: $host:$port\n" .
"Connection: Keep-Alive\n" .
"User-Agent: Netscape-Console/5.01\n" .
"Accept-Language: en\n" .
"Authorization: Basic $auth\n" .
"Content-Length: $length\n" .
"Content-Type: application/x-www-form-urlencoded\n" .
"Content-Transfer-Encoding: 7bit\n";

  print "header = $header\n" if ($verbose);
  print "content = $content\n" if ($verbose);

  # open the connection
  my ($iaddr, $paddr, $proto, $line);

  my $ii = 0;

  $iaddr = inet_aton($host) or die "could not find host $host for http connection: $!";
#  print "iaddr = $iaddr\n";
  $paddr = sockaddr_in($port, $iaddr);
#  print "paddr = $paddr\n";

  $proto = getprotobyname('tcp');
#  print "proto = $proto\n";
  socket(SOCK, PF_INET, SOCK_STREAM, $proto) or die "could not open socket for $host:$port: $!";
#  print "proto = $proto\n";
  CORE::connect(SOCK, $paddr) or die "could not connect to http server $host:$port: $!";

  select SOCK ; $| = 1; select STDOUT; $| = 1;
  #print SOCK "GET / HTTP/1.0\n\n";
  #print SOCK <<EOF;
  #GET / HTTP/1.0
  #
  #EOF
  #print "after sending, now receiving...\n";
  #read(SOCK, $line, 12);
  #print $line, "\n";
  #while (<SOCK>) {
  #  print $_;
  #}

  print SOCK $header, "\n", $content, "\n\n";
  print "after sending, now receiving...\n" if ($verbose);

  my $exitCode = 1;
  my @lines;
  while (<SOCK>) {
	print $_ if ($verbose);
	push @lines, $_;
	if (/^NMC_Status:\s*(\d+)/) {
	  $exitCode = $1;
	  last;
	}
  }
  CORE::close(SOCK);
  if ($exitCode) {
	print "CGI failed with $exitCode: here is the output:\n";
	map { print $_ } @lines;
  }

  return $exitCode;
}

# The general idea here is to use the .inf file method if the server is local, and use
# the CGI method if the server is remote
# pass in a ref to a hash table e.g. like this:
# createInstance({ sroot => "/path", newhost => 'hostname', ....});
# If the sroot is given, it is assumed it is local
#
# required parameters are:
#	newrootpw - new directory manager password
#	newsuffix - the default suffix for the new server
#	newinst - the new instance name (server id)
#	sroot OR cfgdshost, cfgdsport, cfgdsuser, cfgdspwd
#	sroot AND cfgdsuser, cfgdspwd - for remote, cfgdshost and port can be looked up
#	cfgdspwd - this is required for creating a remote directory server
#
# optional parameters are:
#	newhost - default is the localhost
#	newport - default is 389 (must be root or creating remote)
#	newrootdn - default is cn=directory manager
#	newuserid (unix) - default is calculated or looked up
#
# You cannot create a local directory server if the server root is not given or if the
# server root cannot be looked up from the configds.
#
# Returns a new NDSAdminNL object if successful or null if not
sub createInstance {
  my $arg = shift;
  my $status = shift; # ref to a scalar

  ${$status} = 0;

  my %aliases;
  my $myhost = getFQDN(0, \%aliases);
  # if newhost is not set, it will get set to FQDN
  # if newhost is set, but not FQDN, it will get set to FQDN
  # if newhost is already FQDN, it will be returned unchanged
  $arg->{newhost} = getFQDN($arg->{newhost});
  my $isLocal;
  my $verbose = $arg->{verbose};

  if (!$arg->{newhost}) { # no host given, default to local
	$arg->{newhost} = $myhost;
	$isLocal = 1;
  } elsif ($arg->{newhost} eq 'localhost') { # force localhost
	$isLocal = 1;
  } elsif ($arg->{newhost} eq $myhost) { # newhost is localhost
	$isLocal = 1;
  } elsif ($arg->{newhost} =~ /^$myhost\./) { # they match
	$isLocal = 1;
  } elsif ($aliases{$arg->{newhost}}) { # newhost is one of the aliases of localhost
	$isLocal = 1;
  } else {
	$isLocal = 0;
  }

  my $cfgdn = "o=NetscapeRoot";
  if (!$arg->{cfgdshost} || !$arg->{cfgdsport}) {
	if (-f "$arg->{sroot}/shared/config/dbswitch.conf") {
	  open(DBSWITCH, "$arg->{sroot}/shared/config/dbswitch.conf");
	  while (<DBSWITCH>) {
		chop;
		if (/^directory\s+default\s+/) {
		  my $h = my_ldap_url_parse($'); # ' fix for font lock
		  $arg->{cfgdshost} = $h->{host};
		  $arg->{cfgdsport} = $h->{port};
		  $cfgdn = $h->{dn};
		}
	  }
	  close DBSWITCH;
	}
  }

  my $asport;
  my $cfgconn;
  if ($arg->{cfgdshost} && $arg->{cfgdsport}) {
	  # first, see if $cfguser is a full DN or not - if not, look up the DN
	  $cfgconn = new NDSAdminNL($arg->{cfgdshost}, port => $arg->{cfgdsport});
	  print "Error: could not open ldap connection to $arg->{cfgdshost}:$arg->{cfgdsport}\n"
		  if (!$cfgconn);
	  if ($arg->{cfgdspwd} && (!$arg->{cfgdsuser} || ($arg->{cfgdsuser} !~ /\=/))) {
#	my $ent = $cfgconn->search("o=NetscapeRoot", "sub", "(uid=$cfgdsuser)", 0, qw(dn));
#	if (!$ent || (my $rc = $cfgconn->getErrorCode())) {
#	  die "Error: could not find $cfgdsuser in $cfgdshost:$cfgdsport: error $rc";
#	}
		  if ($cfgconn && $arg->{cfgdsuser}) {
			  my $mesg = $cfgconn->search(base => "o=NetscapeRoot", scope => "sub",
										  filter => "(uid=$arg->{cfgdsuser})",
										  attrs => ['dn']);
			  check_mesg($mesg, "Error searching for admin user id " . $arg->{cfgdsuser});
			  my $ent = $mesg->shift_entry;
			  $arg->{cfgdsuser} = $ent->dn();
		  } elsif ($arg->{sroot} && -f "$arg->{sroot}/shared/config/ldap.conf") {
			  open(LDAPCONF, "$arg->{sroot}/shared/config/ldap.conf");
			  while (<LDAPCONF>) {
				  chop;
				  if (/^admnm\s+/) {
					  $arg->{cfgdsuser} = $'; # ' fix font lock
				  }
			  }
			  close LDAPCONF;
		  } elsif ($arg->{cfgdsuser}) {
			  $arg->{cfgdsuser} =
				  "uid=$arg->{cfgdsuser}, ou=Administrators, ou=TopologyManagement, o=NetscapeRoot";
		  }

		  # next, bind to the cfg ds as the cfg user
		  if ($cfgconn && $arg->{cfgdsuser} && $arg->{cfgdspwd}) {
			  $cfgconn = new NDSAdminNL($arg->{cfgdshost}, port => $arg->{cfgdsport},
										binddn => $arg->{cfgdsuser},
										bindpasswd => $arg->{cfgdspwd});
			  if (!$cfgconn) {
				  print "Error: could not bind to $arg->{cfgdshost}:$arg->{cfgdsport} as " .
					  "$arg->{cfgdsuser}:$arg->{cfgdspwd}\n";
			  }
		  }
	  }
  }

  # look up the server root - if we are installing on the local machine, and
  # the server root was not given, look up the server root for the config ds
  # and use it's server root as our server root
  if ($cfgconn && !$arg->{sroot} && $isLocal) {
	my $dn = "cn=config";
	my $mesg = $cfgconn->search(base => $dn, scope => "base", filter => "(objectclass=*)",
								attrs => [ 'nsslapd-instancedir' ]);
	check_mesg($mesg, "Error searching for instance dir",
			   {LDAP_NO_SUCH_OBJECT => LDAP_NO_SUCH_OBJECT});
	my $ent = $mesg->shift_entry;
	if ($ent) {
	  ($arg->{sroot} = $ent->get_value('nsslapd-instancedir')) =~ s|/[^/]+$||;
	}
  }

  if ($isLocal && !$arg->{admin_domain}) {
	if ($arg->{sroot} && -f "$arg->{sroot}/shared/config/ds.conf") {
	  open(DSCONF, "$arg->{sroot}/shared/config/ds.conf");
	  while (<DSCONF>) {
		chop;
		if (/^AdminDomain:\s*/) {
		  $arg->{admin_domain} = $'; # ' fix for font lock
		}
	  }
	  close DSCONF;
	}
  }

  if ($cfgconn) {
	# look up the admin server port on the newhost
	my $dn = $cfgdn;
	if ($arg->{admin_domain}) {
	  $dn = "ou=$arg->{admin_domain}, $dn";
	  if ($arg->{newhost}) {
		$dn = "cn=$arg->{newhost}, $dn";
	  }
	}
	my $filter = "(&(objectclass=nsAdminServer)(serverHostName=$arg->{newhost})";
	$filter = $filter . "(serverRoot=$arg->{sroot})" if ($arg->{sroot});
	$filter = $filter . ")";
	my $mesg = $cfgconn->search(base => $dn, scope => "sub", filter => $filter,
								attrs => [ 'serverRoot']);
	check_mesg($mesg, "Error getting server root from admin server");
	my $asent = $mesg->shift_entry;
	if ($asent) {
	  if (!$arg->{sroot}) {
	    $arg->{sroot} = $asent->get_value('serverRoot');
	  }

	  if (!$arg->{admin_domain}) {
		@rdns = my_ldap_explode_dn($asent->dn, 1);
		$arg->{admin_domain} = $rdns[-2];
	  }

	  $dn = "cn=configuration, " . $asent->dn;
	  $mesg = $cfgconn->search(base => $dn, scope => "base", filter => "(objectclass=*)",
								attrs => ['nsServerPort', 'nsSuiteSpotUser']);
	  check_mesg($mesg, "Error getting admin port and user");
	  my $asent = $mesg->shift_entry;
	  if ($asent) {
		$asport = $asent->get_value("nsServerPort");
		if (! $arg->{newuserid}) {
		  $arg->{newuserid} = $asent->get_value("nsSuiteSpotUser");
		}
	  }
	}
	$cfgconn->disconnect();
  }

  if (!$arg->{newuserid} && $arg->{sroot} && -f "$arg->{sroot}/shared/config/ssusers.conf") {
	open(SSUSERS, "$arg->{sroot}/shared/config/ssusers.conf");
	while (<SSUSERS>) {
	  chop;
	  if (/^SuiteSpotUser\s+/) {
		$arg->{newuserid} = $'; # ' fix for font lock
	  }
	}
	close SSUSERS;
  } elsif (!$arg->{newuserid}) {
	# assume running locally
	if (! $isNT) {
	  $arg->{newuserid} = getpwuid($>);
	} else {
	  $arg->{newuserid} = "nobody";
	}
	if ($arg->{newuserid} eq "root") {
	  $arg->{newuserid} = "nobody";
	}
  }

  $arg->{newport} = 389 if (!$arg->{newport});
  $arg->{newrootdn} = "cn=directory manager" if (!$arg->{newrootdn});
  $arg->{newsuffix} = defaultsuffix($arg->{newhost}) if (!$arg->{newsuffix});
  if (! $isLocal || $arg->{cfgdshost}) {
	  $arg->{admin_domain} = defaultadmindomain($arg->{newhost}) if (!$arg->{admin_domain});
	  $arg->{cfgdspwd} = "dummy" if ($isLocal && !$arg->{cfgdspwd});
	  $arg->{cfgdshost} = $arg->{newhost} if ($isLocal && !$arg->{cfgdshost});
	  $arg->{cfgdsport} = 55555 if ($isLocal && !$arg->{cfgdsport});
  }

  # check for missing required arguments
  my $missing = 0;
  for (qw(newhost newport newrootdn newrootpw newinst newsuffix)) {
	if (!$arg->{$_}) {
	  print "Error: missing required argument $_\n";
	  $missing = 1;
	}
  }

  if (! $isLocal || $arg->{cfgdshost}) {
    for (qw(cfgdshost cfgdsport cfgdsuser cfgdspwd admin_domain)) {
	  if (!$arg->{$_}) {
	    print "Error: missing required argument $_\n";
	    $missing = 1;
	  }
    }
  }

  if (!$isLocal && !$asport) {
	print "Error: missing required argument admin server port\n";
	$missing = 1;
  }

  if ($isLocal && !$arg->{sroot}) {
	print "Error: missing required argument sroot\n";
  }

  if ($missing) {
	print "Error: cannot create new instance\n";
	return 0;
  }

  # see if server already exists
  my $newconn = new NDSAdminNL($arg->{newhost}, port => $arg->{newport},
							  binddn => $arg->{newrootdn},
							  bindpasswd => $arg->{newrootpw},
							  ignore => {LDAP_SERVER_DOWN => LDAP_SERVER_DOWN});
  if ($newconn) {
	$newconn->{isLocal} = $isLocal;
	$newconn->{asport} = $asport;
	$newconn->{cfgdsuser} = $arg->{cfgdsuser};
	$newconn->{cfgdspwd} = $arg->{cfgdspwd};
	print "Warning: server already exists: ", $newconn->toString(),
		" could not create new instance\n";
	${$status} = 1;
	return $newconn;
  }

  # next, construct a hash table with our arguments
  my %cgiargs = (
	servname => $arg->{newhost},
	servport => $arg->{newport},
	rootdn => $arg->{newrootdn},
	rootpw => $arg->{newrootpw},
	servid => $arg->{newinst},
	suffix => $arg->{newsuffix},
	servuser => $arg->{newuserid},
	start_server => 1
  );
  if (! $isLocal || $arg->{cfgdshost}) {
	  $cgiargs{cfg_sspt_uid} = $arg->{cfgdsuser};
	  $cgiargs{cfg_sspt_uid_pw} = $arg->{cfgdspwd};
	  $cgiargs{ldap_url} = "ldap://$arg->{cfgdshost}:$arg->{cfgdsport}/$cfgdn";
	  $cgiargs{admin_domain} = $arg->{admin_domain};
  }
  my $rc;
  if (!$isLocal) {
	$rc = &cgiPost($arg->{newhost}, $asport, $arg->{cfgdsuser},
				   $arg->{cfgdspwd}, "/slapd/Tasks/Operation/Create", $verbose,
				   \%cgiargs);
  } else {
	my $prog = $arg->{sroot} . "/bin/slapd/admin/bin/ds_create";
	if (! -x $prog) {
		$prog = $arg->{sroot} . "/bin/slapd/admin/bin/ds_newinst";
	}
	$rc = &cgiFake($arg->{sroot}, $verbose, $prog,
				   \%cgiargs);
  }

  if (!$rc) { # success - try to create a new NDSAdminNL
	$newconn = new NDSAdminNL($arg->{newhost}, port => $arg->{newport},
							 binddn => $arg->{newrootdn},
							 bindpasswd => $arg->{newrootpw});
	if ($newconn) {
	  $newconn->{isLocal} = $isLocal;
	  $newconn->{asport} = $asport;
	  $newconn->{cfgdsuser} = $arg->{cfgdsuser};
	  $newconn->{cfgdspwd} = $arg->{cfgdspwd};
	}
  }

  return $newconn;
}

# removes an instance of directory server
# - removes the instance directory and all sub directories in the file system
# - cleans up the information in the config DS under o=NetscapeRoot
# - removes the registry entries (on Windows)
# - closes the connection to the server
sub removeInstance {
  my ($self, $verbose) = @_;
  # construct a hash table with our arguments
  my %cgiargs = (
	InstanceName => "slapd-" . $self->{inst}
  );
  print "closing server ", $self->toString(), "\n" if ($verbose);
  $self->disconnect();
  if (!$self->{isLocal} && $self->{asport}) {
	print "removing remote server ", $self->toString(), "\n" if ($verbose);
	my $rc = &cgiPost($self->{host}, $self->{asport}, $self->{cfgdsuser},
					  $self->{cfgdspwd},
					  "/slapd-$self->{inst}/Tasks/Operation/Remove",
					  $verbose, \%cgiargs);
	print "removed remote server ", $self->toString(), " rc = $rc\n" if ($verbose);
  } else {
	print "removing local server ", $self->toString(), "\n" if ($verbose);
	$ENV{SERVER_NAMES} = "slapd-" . $self->{inst};
	my $rc = &cgiFake($self->{sroot}, $verbose,
					  $self->{sroot} . "/bin/slapd/admin/bin/ds_remove",
					  \%cgiargs);
	print "removed local server ", $self->toString(), " rc = $rc\n" if ($verbose);
  }

  return $rc;
}

# removes an instance of directory server
# - removes the instance directory and all sub directories in the file system
# - cleans up the information in the config DS under o=NetscapeRoot
# - removes the registry entries (on Windows)
# - closes the connection to the server
sub removeOtherInstance {
  my ($cfgdsconn, $inst, $verbose) = @_;
  # construct a hash table with our arguments
  my %cgiargs = (
	InstanceName => "slapd-" . $inst
  );
  my $id;
  if (ref($cfgdsconn) eq 'NDSAdminNL') {
	$id = $cfgdsconn->toString();
  } else {
	$id = $cfgdsconn->{sroot};
  }
  if (!$cfgdsconn->{isLocal} && $cfgdsconn->{asport}) {
	print "removing remote server $inst on $id\n" if ($verbose);
	my $rc = &cgiPost($cfgdsconn->{host}, $cfgdsconn->{asport}, $cfgdsconn->{cfgdsuser},
					  $cfgdsconn->{cfgdspwd},
					  "/slapd-$inst/Tasks/Operation/Remove",
					  $verbose, \%cgiargs);
	print "removed remote server $inst on $id rc = $rc\n" if ($verbose);
  } else {
	print "removing local server $inst on $id\n" if ($verbose);
	$ENV{SERVER_NAMES} = "slapd-" . $inst;
	my $rc = &cgiFake($cfgdsconn->{sroot}, $verbose,
					  $cfgdsconn->{sroot} . "/bin/slapd/admin/bin/ds_remove",
					  \%cgiargs);
	print "removed local server $inst on $id rc = $rc\n" if ($verbose);
  }

  return $rc;
}

# setup everything needed to enable replication for a given suffix
# argument - a hashref with the following fields
#	suffix
#	bename - name of backend corresponding to suffix
# optional fields and their default values
#	parent - parent suffix if suffix is a sub-suffix - default is undef
#	ro - put database in read only mode - default is read write
#	type - replica type ($MASTER_TYPE, $HUB_TYPE, $LEAF_TYPE) - default is master
#	legacy - make this replica a legacy consumer - default is no
#	binddn - bind DN of the replication manager user - default is $REPLBINDDN
#	bindcn - bind CN of the replication manager user - default is $REPLBINDCN
#	bindpw - bind password of the repl manager - default is $REPLBINDPW
#	log - if true, replication logging is turned on
#	id - the replica ID - default is an auto incremented number
sub replicaSetupAll {
  my $self = shift;
  my $repArgs = shift;
  $repArgs->{type} = $MASTER_TYPE if (!$repArgs->{type});
  $self->addSuffix($repArgs->{suffix});
  $self->setDBReadOnly("on", $repArgs->{bename}) if ($repArgs->{ro});
  $self->enableReplLogging() if ($repArgs->{log});
  $self->setupChangelog() if ($repArgs->{type} != $LEAF_TYPE);
  $self->setupReplBindDN($repArgs->{binddn}, $repArgs->{bindcn}, $repArgs->{bindpw});
  $self->setDBReadOnly("off", $repArgs->{bename}) if ($repArgs->{ro});
  $self->setupReplica($repArgs);
  $self->setDBReadOnly("on", $repArgs->{bename}) if ($repArgs->{ro});
  $self->setupLegacyConsumer($repArgs->{binddn}, $repArgs->{bindpw}) if ($repArgs->{legacy});
}

# pass this sub two hashrefs - the first one is a hashref suitable to create
# a new instance - see createInstance for more details
# the second is a hashref suitable for replicaSetupAll - see replicaSetupAll
sub createAndSetupReplica {
  my ($createArgs, $repArgs) = @_;

  my $conn = createInstance($createArgs);
  if (!$conn) {
	print "Error: could not create server %{$createArgs}\n";
	return 0;
  }

  $conn->replicaSetupAll($repArgs);

  return $conn;
}

sub findSuffixForEntry {
  my ($self, $entrydn) = @_;
  my $entrydnN = normalizeDN($entrydn);
  my @suffixN = my_ldap_explode_dn($entrydnN, 0);

  # search for the suffix of the entry
  my $done = 0;
  my $suffixdn;
  while (!$suffixdn) {
	my $trysuffix = join(',', @suffixN);
	my $mesg = $self->search(base   => 'cn=mapping tree, cn=config',
							 scope  => 'sub',
							 filter => "(|(cn=$trysuffix)(cn=\"$trysuffix\"))",
							 attrs => ['cn']);
	check_mesg($mesg, "Could not search for mapping tree entry for $trysuffix",
			   {LDAP_NO_SUCH_OBJECT => LDAP_NO_SUCH_OBJECT});
	my $mapent = $mesg->shift_entry;
	if ($mapent) {
	  $suffixdn = $trysuffix;
	} else {
	  shift @suffixN; # remove 1 rdn and try again
	}
  }

  print "Error: could not find suffix for $entrydn\n" if (!$suffixdn);

  return $suffixdn;
}

# see if the given suffix has a parent suffix
sub findParentSuffix {
  my ($self, $suffix) = @_;
  my @rdns = my_ldap_explode_dn($suffix, 0);
  my $nsuffix = normalizeDN($suffix);
  my @nrdns = my_ldap_explode_dn($nsuffix, 0);
  shift @rdns;
  shift @nrdns;
  return 0 if (!@rdns);

  do {
	$suffix = join(',', @rdns);
	$nsuffix = join(',', @nrdns);
	my $mesg = $self->search(base   => 'cn=mapping tree, cn=config',
							 scope  => 'sub',
							 filter => "(|(cn=\"$suffix\")(cn=\"$nsuffix\"))",
							 attrs  => ['cn']);
	check_mesg($mesg, "Error searching for parent suffix");
	my $mapent = $mesg->shift_entry;
	if ($mapent) {
	  return $suffix;
	} else {
	  shift @rdns;
	  shift @nrdns;
	}
  } while (@rdns);

  return 0;
}

sub findAndPrintTombstones {
  my ($self, $suffix) = @_;
  my $mesg = $self->search(base   => $suffix,
						   scope  =>"sub",
						   filter => "(&(objectclass=nsTombstone)(nscpentrydn=*))");
  check_mesg($mesg, "Could not get tombstone entry",
			 {LDAP_NO_SUCH_OBJECT => LDAP_NO_SUCH_OBJECT});
  if (!$mesg->count) {
	print "No tombstones under $suffix\n";
	return;
  }
  while (my $ent = $mesg->shift_entry) {
	$ent->dump;
  }
}

1; # obligatory true return from module
