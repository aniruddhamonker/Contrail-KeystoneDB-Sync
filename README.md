# Keystone projects sync from Contrail DB Snapshot
Tool to sync Keystone projects from contrail's database snapshot file.
Primary use for troubleshooting scenarios in Contrail when attempting to reproduce customer issues in the lab

## Pre-requisites
Before installation please ensure you have "pip" and "git" installed on your system

## Dependencies
keystoneauth1

## Installation
```
$pip install git+https://github.com/aniruddhamonker/Contrail-KeystoneDB-Sync.git
```

## Usage
### Help
```
$dbsync-keystone --help
usage: dbsync-keystone [-h] [-s [SYNC [SYNC ...]]] [-i] [-c] [-d] db_file_path

positional arguments:
  db_file_path          Path and filename of the JSON DB file

optional arguments:
  -h, --help            show this help message and exit
  -s [SYNC [SYNC ...]], --sync [SYNC [SYNC ...]]
                        Provide a list of customer project names to sync with
                        Keystone server
  -i, --dbimport        Only import customer DB. Do not sync Keystone projects
  -c, --cleanup         Delete Keystone projects that were created from
                        customer DB file
  -d, --debug           increase output verbosity

```

### Debug
Running with --debug flag will print debug level messages on the terminal session as well as in the log file.
The default location of the log file is "/var/log/contrail/dbsync-keystone.log"

### Execution
This is the default execution of the script without any options.
Running this way will result in script creating Keystone projects on local server based on the projects defined under Contrail DB snapshot file. It will also update Contrail DB file with UUIDs of the newly created Keystone projects on the local server.
Finally, the script will import the updated Contrail DB file into Contrail and restart the necessary services.

```
$dbsync-keystone --debug <location-of-db-snapshot-file>
```

### DB Import Only
This option only imports the contents of DB snapshot file, does not create any Keystone projects on the local setup.

```
$dbsync-keystone --debug --dbimport <location-of-db-snapshot-file>
```

## Cleanup
This option deletes the keystone projects on local server that were created from contrail DB snapshot file
```
$ dbsync-keystone --debug --cleanup ~/zchg1accnt02.json
```

## Sync
This option only creates keystone projects specified as input arguments. The project names are space seperated with quotes as shown below. This option will create only the specified projects on local Keystone server, update the contrail DB snapshot file with UUIDs of corresponding projects and finally import the DB snapshot file into Contrail.
```
$dbsync-keystone --debug --sync 'Project-name-1' 'Project-name-2' 'Project-name-3' -- <location-of-db-snapshot-file>
```
Please note "--" in the above command used to mark end of project names

## TO-DOs
+ Support DB imports for HA setups
+ Run within Config container in Contrail 5.x setups
+ Take DB snapshots of current state before importing another Contrail DB
