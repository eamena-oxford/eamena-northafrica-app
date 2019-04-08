import os
import unicodecsv
from django.test.runner import DiscoverRunner, dependency_ordered
from django.conf import settings
from arches.db.install import truncate_db, install_db
from tests import test_setup
from django.contrib.auth.models import User, Group


class MyRunner(DiscoverRunner):

    def setup_databases(self, **kwargs):
        return setup_databases(self.verbosity, self.interactive, **kwargs)


def setup_databases(verbosity, interactive, **kwargs):
    """Taken from django.test.runner and modified so it uses our own database setup"""
    from django.db import connections, DEFAULT_DB_ALIAS

    # First pass -- work out which databases actually need to be created,
    # and which ones are test mirrors or duplicate entries in DATABASES
    mirrored_aliases = {}
    test_databases = {}
    dependencies = {}
    default_sig = connections[DEFAULT_DB_ALIAS].creation.test_db_signature()
    for alias in connections:
        connection = connections[alias]
        if connection.settings_dict['TEST_MIRROR']:
            # If the database is marked as a test mirror, save
            # the alias.
            mirrored_aliases[alias] = (
                connection.settings_dict['TEST_MIRROR'])
        else:
            # Store a tuple with DB parameters that uniquely identify it.
            # If we have two aliases with the same values for that tuple,
            # we only need to create the test database once.
            item = test_databases.setdefault(
                connection.creation.test_db_signature(),
                (connection.settings_dict['NAME'], set())
            )
            item[1].add(alias)

            if 'TEST_DEPENDENCIES' in connection.settings_dict:
                dependencies[alias] = (
                    connection.settings_dict['TEST_DEPENDENCIES'])
            else:
                if alias != DEFAULT_DB_ALIAS and connection.creation.test_db_signature() != default_sig:
                    dependencies[alias] = connection.settings_dict.get(
                        'TEST_DEPENDENCIES', [DEFAULT_DB_ALIAS])

    # Second pass -- actually create the databases.
    old_names = []
    mirrors = []

    for signature, (db_name, aliases) in dependency_ordered(
        test_databases.items(), dependencies):
        test_db_name = None
        # Actually create the database for the first connection
        for alias in aliases:
            connection = connections[alias]
            print connection
            if test_db_name is None:
                # Changed just this line from the default django function so that it runs our own setup commands
                test_db_name = setup_db(connection)
                destroy = True
            else:
                connection.settings_dict['NAME'] = test_db_name
                destroy = False
            old_names.append((connection, db_name, destroy))

    for alias, mirror_alias in mirrored_aliases.items():
        mirrors.append((alias, connections[alias].settings_dict['NAME']))
        connections[alias].settings_dict['NAME'] = (
            connections[mirror_alias].settings_dict['NAME'])

    return old_names, mirrors


def setup_db(connection):
    """
    Taken from the setup_db management command but slightly edited to run using the test database name. It will
    also run the test_setup.install() function that will edit and add concepts into the database.
    """

    test_database_name = connection.creation._get_test_db_name()

    db_settings = settings.DATABASES['default']
    db_settings['NAME'] = test_database_name

    truncate_path = os.path.join(settings.ROOT_DIR, 'db', 'install', 'truncate_db.sql')
    install_path = os.path.join(settings.ROOT_DIR, 'db', 'install', 'install_db.sql')
    db_settings['truncate_path'] = truncate_path
    db_settings['install_path'] = install_path

    truncate_db.create_sqlfile(db_settings, truncate_path)
    install_db.create_sqlfile(db_settings, install_path)

    os.system('psql -h %(HOST)s -p %(PORT)s -U %(USER)s -d postgres -f "%(truncate_path)s"' % db_settings)
    os.system('psql -h %(HOST)s -p %(PORT)s -U %(USER)s -d %(NAME)s -f "%(install_path)s"' % db_settings)

    create_groups()
    create_users()

    settings.DATABASES['default']["NAME"] = test_database_name
    connection.settings_dict["NAME"] = test_database_name

    print "DATABASE CREATION STEP DONE - NOW ADDING DATA"

    test_setup.install()

    return test_database_name


def create_groups():
    """
    Creates read and edit groups. Should be same as the command management method in arches.management.commands.packages
    """

    Group.objects.create(name='edit')
    Group.objects.create(name='read')


def create_users():
    """
    Creates anonymous user and adds anonymous and admin user to appropriate groups. Should be same as the command
    management method in arches.management.commands.packages
    """

    anonymous_user = User.objects.create_user('anonymous', '', '')
    read_group = Group.objects.get(name='read')
    anonymous_user.groups.add(read_group)

    edit_group = Group.objects.get(name='edit')

    # remove the default Arches admin user (we want more control over this)
    admin_user = User.objects.get(username='admin')
    admin_user.delete()

    # now create users by iterating the initial users CSV
    if not os.path.isfile(settings.INITIAL_USERS_CONFIG):
        return
    with open(settings.INITIAL_USERS_CONFIG, "rb") as opencsv:
        reader = unicodecsv.DictReader(opencsv)
        print "\nCREATING USERS\n--------------"
        for info in reader:

            # create the user object from info in row
            newuser = User(
                username=info['username'],
                first_name=info['firstname'],
                last_name=info['lastname'],
                email=info['email'],
            )
            if info['staff'].lower().rstrip() == 'yes':
                newuser.is_staff = True
            if info['superuser'].lower().rstrip() == 'yes':
                newuser.is_superuser = True
            newuser.set_password(info['password'])
            newuser.save()

            # once saved, add the user to groups as needed
            for g in info['groups'].split(";"):
                gname = g.lstrip().rstrip()
                if gname == "read":
                    newuser.groups.add(read_group)
                if gname == "edit":
                    newuser.groups.add(edit_group)

            print "  --",newuser.username

