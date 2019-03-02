import json
import argparse
import time
import subprocess as sub
from builtins import property, staticmethod, Exception
from keystoneauth1.identity import v2
from keystoneauth1 import session
from keystoneclient.v2_0 import client
from keystoneauth1 import exceptions as _exc

class KeystoneProject:
    def __init__(self, **kwargs):
        self.auth = v2.Password(username=kwargs.get('username', 'admin'), password=kwargs.get('password', 'Juniper'),
                                tenant_name=kwargs.get('tenant_name', 'admin'), auth_url=kwargs.get('auth_url', None))
        self.sess = session.Session(auth=self.auth)
        self.keystone = client.Client(session=self.sess)
        self.db_file = kwargs.get('db_file', db_file)

    def create_new_projects(self, project_names):
        """
        This method takes in an instance of DatabaseSnapshot class as an argument.
        db_snapshot here is an instance of DatabaseSnapshot.
        :param self: instance of class KeystoneProject
        :param project_names: List of Projects dictionary
        """
        projects = []
        for project in project_names:
            try:
                new_project = self.keystone.tenants.create(tenant_name=project['name'], description="ProjectInfo:{}"
                                                           .format(project['name']), enabled=True)
                projects.append({'name': project['name'], 'old_uuid': project['uuid'], 'new_uuid': new_project.id})
            except Exception as exp:
                print("Error when creating new Project {} : Err: {} -- {}".format(project['name'], type(exp), exp))
        return projects

    def delete_keystone_projects(self, projects_list):
        """
        This method to be used to cleanup/delete the projects that were created from database snapshot file
        :param projects_list: List of projects(Dict) to delete
        :return: None
        """
        for project in projects_list:
            try:
                self.keystone.tenants.delete(project['new_uuid'])
                print("successfully deleted project {}\n".format(project['name']))
            except _exc.NotFound:
                print("project {} not found in Keystone Database\n".format(project['name']))
            except Exception as exp:
                print("Failed to delete project {} due to Exception:{}".format(project['name'], exp)) 
                
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

    def swap_project_uuids(self, projects_list): #type: ([DatabaseSnapshot], List[Dict] -> Str
        """
        This method replaces the original uuids of the projects in the snapshot file with the uuids\
        from local Keystone server. The result is saved in the new file with ".changed" extension.
        :param: self: instance of class DatabaseSnapshot
        :param: projects_list: List of Projects Dictionary
        :return: String: Path and filename of the updated file
        """
        #global db_file
        print("Replacing UUIDs of the customer projects in the snapshot file with the new UUIDs from local \
              Keystone server\n")
        for project in projects_list:
            new_uuid = project['new_uuid']
            new_uuid_dashed = '-'.join([new_uuid[0:8], new_uuid[8:12], new_uuid[12:16], new_uuid[16:20],
                                        new_uuid[20:32]])
            old_uuid_dashed = project['old_uuid']
            old_uuid = old_uuid_dashed.replace('-','')
            try:
                self.json_db_str = self.json_db_str.replace(old_uuid, new_uuid)
                self.json_db_str = self.json_db_str.replace(old_uuid_dashed, new_uuid_dashed)
            except Exception as exp:
                print("Failed to replace UUID for project {}\n{}".format(project['name'], exp))
        changed_db_file = open("{}.changed".format(self.db_snapshot_file_path), "w")
        changed_db_file.write(self.json_db_str)
        changed_db_file.close()
        return "{}.changed".format(self.db_snapshot_file_path)

class DbJsonEximScript:
    def __init__(self):
        self.LOADER_SCRIPT = "/usr/lib/python2.7/dist-packages/cfgm_common/db_json_exim.py"

    @property
    def loader_script(self):
        return self.LOADER_SCRIPT

    @staticmethod
    def stop_contrail_services(*services):
        for service in services:
            print("Stopping {} service...\n".format(service))
            stop_service = sub.Popen('service {} stop || true'.format(service), shell=True, stdout=sub.PIPE, \
                                     stderr=sub.PIPE)
            if stop_service.stderr.read():
                raise "Unable to stop {} process\n{}\n".format(service, stop_service.stderr.read())

    @staticmethod
    def start_contrail_services(*services):
        for service in services:
            start_service = sub.Popen("service {} start".format(service), shell=True, stdout=sub.Popen,
                                      stderr=sub.Popen)
            if start_service.stderr.read():
                raise "Failed to start {} service\n{}\n".format(service, start_service.stderr.read())
            time.sleep(20) if (service == 'cassandra') or (service == 'zookeeper') else time.sleep(5)
        return

    @staticmethod
    def cleanup_zk_and_cassandra_data():
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

    def run_db_exim_script(self, db_file_path):
        """
        This method runs the LOADER script "db_json_exim" and imports the database from the file supplied as an argument
        :param db_file_path: filename/path of Database snapshot file whose contents need to be imported into Cassandra
        :return: None
        """
        print("Running db_json_exim.py to import Database from file '{}'".format(db_file_path))
        script = sub.Popen("python {} {}".format(self.LOADER_SCRIPT, db_file_path), shell=True, stdout=sub.PIPE,\
                               stderr=sub.PIPE)
        if script.stderr.read():
            raise "DB Import Failed\n{}".format(script.stderr.read())
        else:
            return script.stdout.read()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("json_db_file", type=str, help="Path and filename of the JSON DB file")
    args = parser.parse_args()
    db_file_path = args.json_db_file











