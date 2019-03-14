import os
import sys
import json
import argparse
import time
import subprocess as sub
from builtins import property, staticmethod, Exception
from subprocess import Popen
import logging
from keystoneauth1.identity import v2
from keystoneauth1 import session
from keystoneclient.v2_0 import client
from keystoneauth1 import exceptions as _exc

class KeystoneProjects:
    def __init__(self, **kwargs):
        self.auth = v2.Password(username=kwargs.get('username', 'admin'), password=kwargs.get('password', 'Juniper'),
                                tenant_name=kwargs.get('tenant_name', 'admin'), auth_url=kwargs.get('auth_url', None))
        self.sess = session.Session(auth=self.auth)
        self.keystone = client.Client(session=self.sess)
        self.logger = logging.getLogger(__name__)

    def create_new_projects(self, project_names):
        """
        This method creates new projects using the same project names from customer's db snapshot file.
        :param self: instance of class KeystoneProject
        :param project_names: List of Projects dictionary
        """
        new_projects = []
        for project in project_names:
            try:
                new_project = self.keystone.tenants.create(tenant_name=project['name'], description="ProjectInfo:{}"
                                                           .format(project['name']), enabled=True)
                new_projects.append({'name': project['name'], 'old_uuid': project['uuid'], 'new_uuid': new_project.id})
            except Exception as exp:
                logging.exception("Error when creating new Project {} : Err: {}".format(project['name'], type(exp)))
                raise
        return new_projects

    def delete_keystone_projects(self, projects_list):
        """
        This method to be used to cleanup/delete the projects that were created from database snapshot file
        :param projects_list: List of projects(Dict) to delete
        :return: None
        """
        for project in projects_list:
            try:
                self.keystone.tenants.delete(project['new_uuid'])
                logging.debug("successfully deleted project {}\n".format(project['name']))
            except _exc.NotFound:
                logging.exception("project {} not found in Keystone Database\n".format(project['name']))
            except Exception as exp:
                logging.exception("Failed to delete project {} due to Exception:{}".format(project['name'], type(exp)))

class DatabaseSnapshot:
    def __init__(self, db_snapshot_file_path):
        """
        :type db_snapshot_file_path: Path and filename of customer's database snapshot file
        """
        self.db_snapshot_file_path = db_snapshot_file_path
        with open(self.db_snapshot_file_path) as db_snapshot_file:
            self.json_db_str = db_snapshot_file.read()
            self.json_db_dict = json.loads(self.json_db_str)

    def get_existing_projects(self):
        """
        Thi method fetches all the project names and their corresponding UUIDs from customer's DB snapshot file
        :param self: instance of class DatabaseSnapshot
        :return: Dictionary generator of project names and corresponding uuids
        """
        project_dict = self.json_db_dict['cassandra']['config_db_uuid']['obj_fq_name_table']['project']
        for key in project_dict.keys():
            project_name, project_uuid = key.split(":")[1], key.split(":")[2]
            yield {'name': project_name, 'uuid': project_uuid}

    def swap_project_uuids(self, projects_list):
        """
        This method replaces the original uuids of the projects in the snapshot file with the uuids\
        from local Keystone server. The result is saved in the new file with ".changed" extension.
        :param: self: instance of class DatabaseSnapshot
        :param: projects_list: List of Projects Dictionary
        :return: String: Path and filename of the updated file
        """
        for project in projects_list:
            new_uuid = project['new_uuid']
            new_uuid_dashed = '-'.join([new_uuid[0:8], new_uuid[8:12], new_uuid[12:16], new_uuid[16:20],
                                        new_uuid[20:32]])
            old_uuid_dashed = project['old_uuid']
            old_uuid = old_uuid_dashed.replace('-','')
            try:
                self.json_db_str = self.json_db_str.replace(old_uuid, new_uuid)
                self.json_db_str = self.json_db_str.replace(old_uuid_dashed, new_uuid_dashed)
            except Exception:
                logging.exception("Failed to replace UUID for project {}\n".format(project['name']))
        changed_db_file = open("{}.changed".format(self.db_snapshot_file_path), "w")
        changed_db_file.write(self.json_db_str)
        changed_db_file.close()
        return "{}.changed".format(self.db_snapshot_file_path)

class DbJsonEximScript:
    def __init__(self):
        self.LOADER_SCRIPT = "/usr/lib/python2.7/dist-packages/cfgm_common/db_json_exim.py"
        if not os.path.isfile(self.LOADER_SCRIPT):
            logging.error("FileNotFound: Could not find db_json_exim.py script")
            raise Exception()

    @property
    def loader_script(self):
        return self.LOADER_SCRIPT

    @staticmethod
    def _stop_contrail_services(*services):
        for service in services:
            logging.debug("Stopping {} service...\n".format(service))
            stop_service = sub.Popen('service {} stop'.format(service), shell=True, stderr=sub.PIPE,
                                     stdout=sub.PIPE)
            if stop_service.stderr.read():
                logging.error("Unable to stop {} process\n{}\n".format(service, stop_service.stderr.read()))
                raise
        time.sleep(10)

    @staticmethod
    def _start_contrail_services(*services):
        for service in services:
            start_service = sub.Popen("service {} start".format(service), shell=True, stdout=sub.Popen,
                                      stderr=sub.Popen)
            if start_service.stderr.read():
                raise "Failed to start {} service\n{}\n".format(service, start_service.stderr.read())
            time.sleep(10)
        return

    @staticmethod
    def _cleanup_zk_and_cassandra_data():
        print('Cleaning data directories of Zookeeper and Cassandra\n')
        cleanup_zk = sub.Popen('rm -rf /var/lib/zookeeper/version-2/*', shell=True, stdout=sub.PIPE, stderr=sub.PIPE)
        time.sleep(2)
        if cleanup_zk.stderr.read():
            raise "Failed to delete Zookeeper data\n{}\n".format(cleanup_zk.stderr.read())
        cleanup_cassandra = sub.Popen('rm -rf /var/lib/cassandra/*', shell=True, stdout=sub.PIPE, stderr=sub.PIPE)
        time.sleep(2)
        if cleanup_cassandra.stderr.read():
            raise "Failed to delete Cassandra DB\n{}\n".format(cleanup_cassandra.stderr.read())
        return

    def run_db_exim_script(self, db_file_path, verbosity):
        """
        This method stops necessary contrail services, cleans data directories of zookeeper and Cassandra, runs the LOADER script "db_json_exim.py" to import\
        the database from the file provided as an argument; and finally restarts all the stopped services
        :param db_file_path: filename/path of Database snapshot file whose contents need to be imported into Cassandra
        :param verbosity: prints debug level messages if set to 1
        :return: String
        """
        print "Preparing to import database to Contrail\n" if verbosity == 1
        print "Stopping contrail services\n" if verbosity == 1
        self._stop_contrail_services("supervisor-config", "cassandra", "zookeeper", "kafka")

        print "Erasing zookeeper and Cassandra data\n" if verbosity == 1
        self._cleanup_zk_and_cassandra_data()

        print "Starting zookeeper and cassandra services\n" if verbosity == 1
        self._start_contrail_services("zookeeper", "cassandra")

        print "Importing database to Contrail\n" if verbosity == 1
        print("Running db_json_exim.py to import Database from file '{}'".format(db_file_path)) if verbosity == 1
        script = sub.Popen("python {} --import-from {}".format(self.LOADER_SCRIPT, db_file_path), shell=True,
                           stdout=sub.PIPE, stderr=sub.PIPE)  # type: Popen
        if script.stderr.read():
            raise "DB Import Failed\n{}".format(script.stderr.read())
        else:
            print script.stdout.read()
        time.sleep(5)
        print("Database import Successful\n")

        print "start Kafka and Supervisor-config services\n" if verbosity == 1
        self._start_contrail_services("kafka", "supervisor-config")

        print "restarting Analytics Node\n" if verbosity == 1
        self._stop_contrail_services("supervisor-analytics")
        self._start_contrail_services("supervisor-analytics")
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("json_db_file", required=True, help="Path and filename of the JSON DB file")
    parser.add_argument("-s", "--sync", nargs='+', help="provide a list of customer project names \
                        to sync with Keystone server")
    parser.add_argument("-i", "--dbimport", help="only import customer DB. Do not sync Keystone projects")
    parser.add_argument("-p", "--projects")
    parser.add_argument("-v", "--verbosity", action="count", help="increase output verbosity")
    args = parser.parse_args()

    #create logger
    logger = logging.getLogger(__name__)

    try:
        openstack_creds = {
            "username" : os.environ["OS_USERNAME"],
            "password" : os.environ["OS_PASSWORD"],
            "tenant_name" : os.environ["OS_TENANT_NAME"],
            "auth_url" : os.environ["OS_AUTH_URL"]
        }
    except Exception as KeyErr:
        print("KeyError {}: Import Openstack environment variables\n".format(KeyErr))
        sys.exit(1)

    keystone_projects = KeystoneProjects(**openstack_creds)
    database_snapshot = DatabaseSnapshot(args.json_db_file)
    db_script = DbJsonEximScript()

    if args.dbimport:
        db_script.run_db_exim_script(args.json_db_file, args.verbosity)
        return
    if args.sync:
        customer_projects = [{'name': project} for project in args.sync]
    else:
        customer_projects = [project for project in database_snapshot.get_existing_projects()]
    print "Creating new projects on local Keystone server\n" if args.verbosity == 1
    new_projects = keystone_projects.create_new_projects(customer_projects)
    print("Successfully created {} projects on local Keystone server\n".format(len(new_projects))) \
        if args.verbosity == 1

    print "Updating customer Database file with UUIDs of the projects from local Keystone server\n" \
        if args.verbosity == 1
    updated_json_db_file_path = database_snapshot.swap_project_uuids(new_projects)

    #import the updated database file in Contrail using db_json_exim.py script
    db_script.run_db_exim_script(updated_json_db_file_path, args.verbosity)




























