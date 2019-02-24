import json
import argparse
import re
import subprocess as sub
from keystoneauth1.identity import v2
from keystoneauth1 import session
from keystoneclient.v2_0 import client
from keystoneauth1 import exceptions as _exc

parser = argparse.ArgumentParser()
parser.add_argument("json_db_file", type=str, help="Filename of the JSON DB file")
args = parser.parse_args()
db_file = args.json_db_file


class KeystoneProject:
    def __init__(self, **kwargs):
        self.auth = v2.Password(username=kwargs.get('username', 'admin'), password=kwargs.get('password', 'Juniper'),
                                tenant_name=kwargs.get('tenant_name', 'admin'), auth_url=kwargs.get('auth_url', None))
        self.sess = session.Session(auth=self.auth)
        self.keystone = client.Client(session=self.sess)
        self.db_file = kwargs.get('db_file', db_file)

    def create_new_projects(self, project_names):
        #type: (KeystoneProject, Generator[Dict]) -> List[Dict]
        '''
        This method takes in an instaance of DatabaseSnapshot class as an argument.
        db_snapshot here is an instance of DatabaseSnapshot.
        '''
        projects = []
        for project in project_names:
            try:
                new_project = self.keystone.tenants.create(tenant_name=project['name'], description="ProjectInfo:{}"
                                                           .format(project['name']), enabled=True)
                projects.append({'name': project['name'], 'old_uuid': project['uuid'], 'new_uuid': new_project.id})
            except Exception as exp:
                print("Error when creating new Project {} : Err: {} -- {}".format(project['name'], type(exp), exp))
        return projects

    def delete_keystone_projects(self, projects_list): #type: (Instance[KeystoneProject], List[Dict]) -> None
        '''
        This method to be used to cleanup/delete the projects that were created from database snapshot file
        '''
        for project in projects_list:
            try:
                self.keystone.tenants.delete(project['new_uuid'])
                print("successfully deleted project {}\n".format(project['name']))
            except _exc.NotFound:
                print("project {} not found in Keystone Database\n".format(project['name']))
            except Exception as exp:
                print("Failed to delete project {} due to Exception:{}".format(project['name'], exp)) 
                
class DatabaseSnapshot:
    def __init__(self, db_file):
        self.db_file = db_file
        with open(self.db_file) as db_file:
            self.json_db_str = db_file.read()
            self.json_db_dict = json.loads(self.json_db_str)

    def get_existing_projects(self):  #type: (Instance[DatabaseSnapshot]) -> Generator[Dict]
        project_dict = self.json_db_dict['cassandra']['config_db_uuid']['obj_fq_name_table']['project']
        for key in project_dict.keys():
            project_name, project_uuid = key.split(":")[1], key.split(":")[2]
            yield {'name': project_name, 'uuid': project_uuid}

    def swap_project_uuids(self, projects_list): #type: (Instance[DatabaseSnapshot], List[Dict] -> None
        '''
        This method replaces the original uuids of the projects in the snapshot file with the uuids\
        from local Keystone server. The result is saved in the new file with ".changed" extension.
        '''
        global db_file
        print("Replacing UUIDs of the customer projects in the snapshot file with the new UUIDs from local \
              Keystone server\n")
        for project in projects_list:
            new_uuid = project['new_uuid']
            new_uuid_dashed = '-'.join([new_uuid[0:8], new_uuid[8:12], new_uuid[12:16], new_uuid[16:20], \
                                        new_uuid[20:32]])
            old_uuid_dashed = project['old_uuid']
            old_uuid = old_uuid_dashed.replace('-','')
            try:
                self.json_db_str = db_file_read.replace(old_uuid, new_uuid)
                self.json_db_str = db_file_read.replace(old_uuid_dashed, new_uuid_dashed)
            except Exception as exp:
                print("Failed to replace UUID for project {}\n{}".format(project['name']), exp)
            with open(db_file+".changed", "w") as new_db_file:
                new_db_file.write(self.json_db_str)
            return

class DbJsonEximScript(object):
    def __init__(self):
        self.LOADER_SCRIPT = "/usr/lib/python2.7/dist-packages/cfgm_common/db_json_exim.py"

    @property
    def loader_script(self):
        return self.LOADER_SCRIPT

    @staticmethod
    def stop_contrail_services():
        print("Stopping Contrail config services...\n")
        stop_config = sub.Popen('service supervisor-config stop || true', shell=True, stdout=sub.PIPE, stderr=sub.PIPE)
        if stop_config.stderr.read():
            raise "Unable to stop the supervisor-config process\n{}\n".format(stop_config.stderr.read())
        print("Stopping Cassandra Database Services...\n")
        stop_cassandra = sub.Popen('service cassandra stop', shell=True, stdout=sub.PIPE, stderr=sub.PIPE)
        if stop_cassandra.stderr.read():
            raise"Unable to stop Cassandra\n{}\n".format(stop_cassandra.stderr.read())
        print("stopping Zookeeper service...\n")
        stop_zk = sub.Popen("service zookeeper stop", shell=True, stdout=sub.PIPE, stderr=sub.PIPE)
        if stop_zk.stderr.read():
            raise "Unable to stop zookeeper services\n{}\n".format(stop_zk.stderr.read():)
        print("Stopping Kafka service...\n")
        stop_kafka = sub.Popen("service kafka stop", shell=True, stdout=sub.PIPE, stderr=sub.PIPE)
        if stop_kafka.stderr.read():
            raise "Unable to stop Kafka service\n{}\n".format(stop_kafka.stderr.read())

    @staticmethod
    def cleanup_zk_and_cassandra_data():
        print('Cleaning data directories of Zookeeper and Cassandra\n')
        cleanup_zk = sub.Popen('rm -rf /var/lib/zookeeper/version-2/*', shell=True, stdout=sub.PIPE, stderr=sub.PIPE)
        if cleanup_zk.stderr.read():
            raise "Failed to delete Zookeeper data\n{}\n".format(cleanup_zk.stderr.read())
        cleanup_cassandra = sub.Popen('rm -rf /var/lib/cassandra/*', shell=True, stdout=sub.PIPE, stderr=sub.PIPE)
        if cleanup_cassandra.stderr.read():
            raise "Failed to delete Cassandra DB\n{}\n".format(cleanup_cassandra.stderr.read())

    @staticmethod
    def start_zk_and_cassandra_services():
        print("Starting Zookeeper and Cassandra Services...\n")
        start_zk = sub.Popen("service zookeeper start", shell=True, stdout=sub.Popen, stderr=sub.Popen)
        if start_zk.stderr.read():
            raise "Failed to start Zookeeper service\n{}\n".format(start_zk.stderr.read())
        start_cassandra = sub.Popen("service cassandra start", shell=True, stdout=sub.Popen, stderr=sub.PIPE)
        if start_cassandra.stderr.read():
            raise "Failed to start Cassandra service\n{}\n".format(start_cassandra.stderr.read())

    
