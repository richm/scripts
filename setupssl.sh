#!/bin/sh

if [ "$1" -a -d "$1" ] ; then
    echo "Using $1 as alias directory"
else
    sroot=/opt/fedora-ds
    cd $sroot/alias
fi

if [ "$2" ] ; then
    ldapport=$2
else
    ldapport=389
fi

me=`whoami`
if [ "$me" = "root" ] ; then
    isroot=1
fi

# see if there are already certs and keys
prefix=`ls -1 slapd-*-cert8.db | head -1 | sed -e s/cert8.db\$//`
if [ -f ${prefix}cert8.db ] ; then
    # look for CA cert
    if test -n "$prefix" ; then
        prefixarg="-P $prefix"
    fi
    if ../shared/bin/certutil -L $prefixarg -d . -n "CA certificate" 2> /dev/null ; then
        echo "Using existing CA certificate"
    else
        echo "No CA certificate found - will create new one"
        needCA=1
    fi

    # look for server cert
    if ../shared/bin/certutil -L $prefixarg -d . -n "Server-Cert" 2> /dev/null ; then
        echo "Using existing directory Server-Cert"
    else
        echo "No Server Cert found - will create new one"
        needServerCert=1
    fi

    # look for admin server cert
    if ../shared/bin/certutil -L $prefixarg -d . -n "server-cert" 2> /dev/null ; then
        echo "Using existing admin server-cert"
    else
        echo "No Admin Server Cert found - will create new one"
        needASCert=1
    fi
fi

if test -z "$needCA" -a -z "$needServerCert" -a -z "$needASCert" ; then
    echo "No certs needed - exiting"
    exit 0
fi

# get our user and group
if test -n "$isroot" ; then
    uid=`/bin/ls -ald . | awk '{print $3}'`
    gid=`/bin/ls -ald . | awk '{print $4}'`
fi

# 2. Create a password file for your security token password:
if [ -f pwdfile.txt ] ; then
    echo "Using existing pwdfile.txt"
else
    echo "Creating password file for security token"
    (ps -ef ; w ) | sha1sum | awk '{print $1}' > pwdfile.txt
    if test -n "$isroot" ; then
        chown $uid:$gid pwdfile.txt
    fi
    chmod 400 pwdfile.txt
fi

# 3. Create a "noise" file for your encryption mechanism: 
if [ -f noise.txt ] ; then
    echo "Using existing noise.txt file"
else
    echo "Creating noise file"
    (w ; ps -ef ; date ) | sha1sum | awk '{print $1}' > noise.txt
    if test -n "$isroot" ; then
        chown $uid:$gid noise.txt
    fi
    chmod 400 noise.txt
fi

# 4. Create the key3.db and cert8.db databases:
if [ ! -f cert8.db ] ; then
    echo "Creating initial key and cert db"
    ../shared/bin/certutil -N -d . -f pwdfile.txt
    if test -n "$isroot" ; then
        chown $uid:$gid key3.db cert8.db
    fi
    chmod 600 key3.db cert8.db
fi

if test -n "$needCA" ; then
# 5. Generate the encryption key:
    echo "Creating encryption key for CA"
    ../shared/bin/certutil -G -d . -z noise.txt -f pwdfile.txt
# 6. Generate the self-signed certificate: 
    echo "Creating self-signed CA certificate"
# note - the basic constraints flag (-2) is required to generate a real CA cert
# it asks 3 questions that cannot be supplied on the command line
    ( echo y ; echo ; echo y ) | ../shared/bin/certutil -S -n "CA certificate" -s "cn=CAcert" -x -t "CT,," -m 1000 -v 120 -d . -z noise.txt -f pwdfile.txt -2
# export the CA cert for use with other apps
    echo Exporting the CA certificate to cacert.asc
    ../shared/bin/certutil -L -d . -n "CA certificate" -a > cacert.asc
fi

if test -n "$needServerCert" ; then
# 7. Generate the server certificate:
    myhost=`hostname --fqdn`
    echo "Generating server certificate for Fedora Directory Server on host $myhost"
    echo Using fully qualified hostname $myhost for the server name in the server cert subject DN
    echo Note: If you do not want to use this hostname, edit this script to change myhost to the
    echo real hostname you want to use
    ../shared/bin/certutil -S -n "Server-Cert" -s "cn=$myhost,ou=Fedora Directory Server" -c "CA certificate" -t "u,u,u" -m 1001 -v 120 -d . -z noise.txt -f pwdfile.txt
fi

if test -n "$needASCert" ; then
# Generate the admin server certificate
    echo Creating the admin server certificate
    ../shared/bin/certutil -S -n "server-cert" -s "cn=$myhost,ou=Fedora Administration Server" -c "CA certificate" -t "u,u,u" -m 1002 -v 120 -d . -z noise.txt -f pwdfile.txt

# export the admin server certificate/private key for import into its key/cert db
    echo Exporting the admin server certificate pk12 file
    ../shared/bin/pk12util -d . -o adminserver.p12 -n server-cert -w pwdfile.txt -k pwdfile.txt
    if test -n "$isroot" ; then
        chown $uid:$gid adminserver.p12
    fi
    chmod 400 adminserver.p12
fi


if test -n "$prefix" ; then
# Copy the key3.db and cert8.db you created to the default databases created at Directory Server installation: 
# assume there is already the default empty key and cert db for the directory instance
    echo Creating real key and cert db for directory server
    keydb=`ls -1 slapd-*-key3.db | head -1`
    certdb=`ls -1 slapd-*-cert8.db | head -1`
# backup the old one, just in case
    mv $keydb $keydb.bak
    mv $certdb $certdb.bak
# move over the new ones
    mv key3.db $keydb
    mv cert8.db $certdb
fi

# create the pin file
if [ ! -f ${prefix}pin.txt ] ; then
    echo Creating pin file for directory server
    pinfile=`echo $keydb | sed -e s/key3.db/pin.txt/`
    echo 'Internal (Software) Token:'`cat pwdfile.txt` > $pinfile
    if test -n "$isroot" ; then
        chown $uid:$gid $pinfile
    fi
    chmod 400 $pinfile
else
    echo Using existing ${prefix}pin.txt
fi

# create the admin server key/cert db
asprefix=`echo $prefix | sed -e s/slapd/admin-serv/`
if [ ! -f ${asprefix}cert8.db ] ; then
    echo Creating key and cert db for admin server $asprefix
    ../shared/bin/certutil -N -d . -P $asprefix -f pwdfile.txt
    if test -n "$isroot" ; then
        chown $uid:$gid admin-serv-*.db
    fi
    chmod 600 admin-serv-*.db
fi

if test -n "$needASCert" ; then
# import the admin server key/cert
    echo "Importing the admin server key and cert (created above)"
    ../shared/bin/pk12util -d . -P $asprefix -n server-cert -i adminserver.p12 -w pwdfile.txt -k pwdfile.txt

# import the CA cert to the admin server cert db
    echo Importing the CA certificate from cacert.asc
    ../shared/bin/certutil -A -d . -P $asprefix -n "CA certificate" -t "CT,," -a -i cacert.asc
fi

if [ ! -f password.conf ] ; then
# create the admin server password file
    echo Creating the admin server password file
    echo 'internal:'`cat pwdfile.txt` > password.conf
    if test -n "$isroot" ; then
        chown $uid:$gid password.conf
    fi
    chmod 400 password.conf
fi

# tell admin server to use the password file
echo Enabling the use of a password file in admin server
sed -e "s@^NSSPassPhraseDialog .*@NSSPassPhraseDialog file:`pwd`/password.conf@" ../admin-serv/config/nss.conf > /tmp/nss.conf && mv /tmp/nss.conf ../admin-serv/config/nss.conf
if test -n "$isroot" ; then
    chown $uid:$gid ../admin-serv/config/nss.conf
fi
chmod 400 ../admin-serv/config/nss.conf

# enable SSL in the directory server
echo "Enabling SSL in the directory server - when prompted, provide the directory manager password"
ldapmodify -x -h localhost -p $ldapport -D "cn=directory manager" -W <<EOF
dn: cn=encryption,cn=config
changetype: modify
replace: nsSSL3
nsSSL3: on
-
replace: nsSSLClientAuth
nsSSLClientAuth: allowed
-
add: nsSSL3Ciphers
nsSSL3Ciphers: -rsa_null_md5,+rsa_rc4_128_md5,+rsa_rc4_40_md5,+rsa_rc2_40_md5,
 +rsa_des_sha,+rsa_fips_des_sha,+rsa_3des_sha,+rsa_fips_3des_sha,+fortezza,
 +fortezza_rc4_128_sha,+fortezza_null,+tls_rsa_export1024_with_rc4_56_sha,
 +tls_rsa_export1024_with_des_cbc_sha
-
add: nsKeyfile
nsKeyfile: alias/$keydb
-
add: nsCertfile
nsCertfile: alias/$certdb

dn: cn=config
changetype: modify
add: nsslapd-security
nsslapd-security: on
-
replace: nsslapd-ssl-check-hostname
nsslapd-ssl-check-hostname: off

dn: cn=RSA,cn=encryption,cn=config
changetype: add
objectclass: top
objectclass: nsEncryptionModule
cn: RSA
nsSSLPersonalitySSL: Server-Cert
nsSSLToken: internal (software)
nsSSLActivation: on

EOF

echo "Done.  You must restart the directory server and the admin server for the changes to take effect."
