import os
import sys
import json
import argparse
import time
import subprocess as sub
#from builtins import property, Exception, classmethod, len, open
import logging
from keystoneauth1.identity import v2
from keystoneauth1 import session
from keystoneclient.v2_0 import client
from keystoneauth1 import exceptions as _exc

class KeystoneProjects:
    def __init__(self, logger, **kwargs):
        self.auth = v2.Password(username=kwargs.get('username', 'admin'), password=kwargs.get('password', 'Juniper'),
                                tenant_name=kwargs.get('tenant_name', 'admin'), auth_url=kwargs.get('auth_url', None))
        self.sess = session.Session(auth=self.auth)
        self.keystone = client.Client(session=self.sess)
        self.__logger = logger

    def create_new_projects(self, project_names):
        """
        This method creates new projects using the same project names from customer's db snapshot file.
        :param self: instance of class KeystoneProject
        :param project_names: List of Projects dictionary
        """
        new_projects = []
        existing_projects = [existing_project.name for existing_project in self.keystone.tenants.list()]
        for project in project_names:
            if project['name'] in existing_projects:
                self.__logger.debug("Project {} already exist in Keystone. Skipping...".format(project['name']))
                continue
            try:
                new_project = self.keystone.tenants.create(tenant_name=project['name'], description="ProjectInfo:{}"
                                                           .format(project['name']), enabled=True)
                new_projects.append({'name': project['name'], 'old_uuid': project['uuid'], 'new_uuid': new_project.id})
            except Exception:
                self.__logger.exception("Error when creating new Project {}\nInitiating Cleanup..."\
                                        .format(project['name']))
                self.delete_keystone_projects(new_projects)    #Perform Cleanup of the new projects created
                raise
        return new_projects

    def delete_keystone_projects(self, projects_list, cleanup=False):
        """
        This method to be used to cleanup/delete the projects that were created from database snapshot file
        :param projects_list: List of projects(Dict) to delete
        :param cleanup: set to True if this method is to be used for cleanup option of the script
        :return: None
        """
        project_uuid = 'uuid' if cleanup else 'new_uuid'  # type:String
        for project in projects_list:
        #Making exception case for admin and demo projects which are default in Openstack and Contrail

            try:
                self.keystone.tenants.delete(project[project_uuid])
                self.__logger.debug("successfully deleted project {}".format(project['name']))
            except _exc.NotFound:
                self.__logger.exception("project {} not found in Keystone Database".format(project['name']))
            except Exception:
                self.__logger.exception("Failed to delete project {}".format(project['name']))
        return

class DatabaseSnapshot:
    def __init__(self, logger, db_snapshot_file_path):
        """
        :type db_snapshot_file_path: Path and filename of customer's database snapshot file
        """
        self.db_snapshot_file_path = db_snapshot_file_path
        self.__logger = logger
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
            self.__logger.debug("Replacing UUID for project: {}".format(project['name']))
            try:
                self.json_db_str = self.json_db_str.replace(old_uuid, new_uuid)
                self.json_db_str = self.json_db_str.replace(old_uuid_dashed, new_uuid_dashed)
            except Exception:
                self.__logger.exception("Failed to replace UUID for project {}".format(project['name']))
        changed_db_file = open("{}.changed".format(self.db_snapshot_file_path), "w")
        changed_db_file.write(self.json_db_str)
        changed_db_file.close()
        return "{}.changed".format(self.db_snapshot_file_path)

class DbJsonEximScript:
    __logger = logging.getLogger(name="DbJsonEximScript")
    def __init__(self, cls):
        self.LOADER_SCRIPT = "/usr/lib/python2.7/dist-packages/cfgm_common/db_json_exim.py"
        if not os.path.isfile(self.LOADER_SCRIPT):
            cls.__logger.error("FileNotFound: Could not find db_json_exim.py script")
            raise Exception

    @property
    def loader_script(self):
        return self.LOADER_SCRIPT

    @classmethod
    def _stop_contrail_services(cls, *services):
        for service in services:
            cls.__logger.debug("Stopping {} service...\n".format(service))
            stop_service = sub.Popen('service {} stop'.format(service), shell=True, stderr=sub.PIPE,
                                     stdout=sub.PIPE)
            if stop_service.stderr.read():
                cls.__logger.exception("Unable to stop {} process\n{}\n".format(service, stop_service.stderr.read()))
                raise Exception("Error Stopping Service")
        time.sleep(10)

    @classmethod
    def _start_contrail_services(cls, *services):
        for service in services:
            start_service = sub.Popen("service {} start".format(service), shell=True, stdout=sub.Popen,
                                      stderr=sub.Popen)
            if start_service.stderr.read():
                cls.__logger.exception("Failed to start {} service\n{}\n".format(service, start_service.stderr.read()))
                raise Exception("Error Starting Service")
            time.sleep(10)
        return

    @classmethod
    def _cleanup_zk_and_cassandra_data(cls):
        cls.__logger.debug('Cleaning data directories of Zookeeper and Cassandra\n')
        cleanup_zk = sub.Popen('rm -rf /var/lib/zookeeper/version-2/*', shell=True, stdout=sub.PIPE, stderr=sub.PIPE)
        time.sleep(2)
        if cleanup_zk.stderr.read():
            cls.__logger.exception("Failed to delete Zookeeper data\n{}\n".format(cleanup_zk.stderr.read()))
            raise Exception("ZkCleanupFailed")
        cleanup_cassandra = sub.Popen('rm -rf /var/lib/cassandra/*', shell=True, stdout=sub.PIPE, stderr=sub.PIPE)
        time.sleep(2)
        if cleanup_cassandra.stderr.read():
            cls.__logger.exception("Failed to delete Cassandra DB\n{}\n".format(cleanup_cassandra.stderr.read()))
            raise Exception("CassandraCleanupFailed")
        return

    def run_db_exim_script(self, cls, db_file_path):
        """
        This method stops necessary contrail services, cleans data directories of zookeeper and Cassandra,
        runs the LOADER script "db_json_exim.py" to import the database from the file provided as an argument;
        and finally restarts all the stopped services
        :param db_file_path: filename/path of Database snapshot file whose contents need to be imported into Cassandra
        :param cls: reference to Class
        :return: String
        """
        cls.__logger.debug("Preparing to import database to Contrail")
        cls.__logger.debug("Stopping contrail services")
        self._stop_contrail_services("supervisor-config", "cassandra", "zookeeper", "kafka")

        cls.__logger.debug("Erasing zookeeper and Cassandra data")
        self._cleanup_zk_and_cassandra_data()

        cls.__logger.debug("Starting zookeeper and cassandra services")
        self._start_contrail_services("zookeeper", "cassandra")

        cls.__logger.debug("Importing database to Contrail")
        cls.__logger.debug("Running db_json_exim.py to import Database from file '{}'".format(db_file_path))
        script = sub.Popen("python {} --import-from {}".format(self.LOADER_SCRIPT, db_file_path), shell=True,
                           stdout=sub.PIPE, stderr=sub.PIPE)
        if script.stderr.read():
            cls.__logger.error("DB Import Failed\n{}".format(script.stderr.read()))
            raise Exception("DBImportFailure")
        else:
            cls.__logger.debug(script.stdout.read())
        time.sleep(5)
        cls.__logger.debug("Database import Successful\n")

        cls.__logger.debug("start Kafka and Supervisor-config services\n")
        self._start_contrail_services("kafka", "supervisor-config")

        cls.__logger.debug("restarting Analytics Node\n")
        self._stop_contrail_services("supervisor-analytics")
        self._start_contrail_services("supervisor-analytics")
        return

class PythonLogger:
    def __init__(self, log_level=logging.INFO):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)
        fh = logging.FileHandler("/var/log/contrail/KeystoneDB_sync.log")
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)')
        fh.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(fh)
        self.logger.addHandler(console_handler)

    def get_logger(self):
        return self.logger

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("db_file_path", help="Path and filename of the JSON DB file")
    parser.add_argument("-s", "--sync", nargs='+', help="Provide a list of customer project names\
                        to sync with Keystone server")
    parser.add_argument("-i", "--dbimport", help="Only import customer DB. Do not sync Keystone projects")
    parser.add_argument("-c", "--cleanup", help="Delete Keystone projects that were created from customer DB file")
    parser.add_argument("-d", "--debug", help="increase output verbosity")
    args = parser.parse_args()
    #create logger under main() and use the same logger across all instantiated objects
    main_logger = PythonLogger(logging.DEBUG).get_logger() if args.debug else PythonLogger().get_logger()
    #test for sourcing openstack environment
    try:
        openstack_creds = {
            "username" : os.environ["OS_USERNAME"],
            "password" : os.environ["OS_PASSWORD"],
            "tenant_name" : os.environ["OS_TENANT_NAME"],
            "auth_url" : os.environ["OS_AUTH_URL"]
        }
    except Exception as KeyErr:
        main_logger.exception("KeyError {}: Import Openstack environment variables\n".format(KeyErr))
        sys.exit(1)
    #instantiate classes
    keystone_projects = KeystoneProjects(main_logger, **openstack_creds)
    database_snapshot = DatabaseSnapshot(main_logger, args.db_file_path)
    db_script = DbJsonEximScript(DbJsonEximScript)
    if args.cleanup:
        main_logger.debug("Initiating deletes of Keystone Projects")
        cleanup_projects = [project for project in database_snapshot.get_existing_projects()]
        keystone_projects.delete_keystone_projects(cleanup_projects, cleanup=True)

    if args.dbimport:
        db_script.run_db_exim_script(DbJsonEximScript, args.json_db_file)
        return
    if args.sync:
        customer_projects = [{'name': project} for project in args.sync]
    else:
        customer_projects = [project for project in database_snapshot.get_existing_projects()]
    main_logger.debug("Creating new projects on local Keystone server")
    new_projects = keystone_projects.create_new_projects(customer_projects)
    main_logger.debug("Successfully created {} projects on local Keystone server".format(len(new_projects)))
    #update customer database file with new project UUIDs from local Keystone server
    main_logger.debug("Updating customer Database file with UUIDs of the projects from local Keystone server")
    updated_json_db_file_path = database_snapshot.swap_project_uuids(new_projects)
    #import the updated database file in Contrail using db_json_exim.py script
    db_script.run_db_exim_script(updated_json_db_file_path, args.verbosity)

if __name__ == '__main__':
    main()


























