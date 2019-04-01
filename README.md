# Keystone DB Sync from Contrail DB Snapshot
Tool to sync Keystone projects from contrail's database snapshot file.
Primary use for troubleshooting scenarios in Contrail when attempting to reproduce customer issues in the lab

## Pre-requisites
Before installation please ensure you have "pip" and "git" installed on your system



## Running the script
### Help
```
$python sync_keystone.py --help

usage: sync_keystone.py [-h] [-s SYNC [SYNC ...]] [-i] [-c] [-d] db_file_path

positional arguments:
  db_file_path          Path and filename of the JSON DB file

optional arguments:
  -h, --help            show this help message and exit
  -s SYNC [SYNC ...], --sync SYNC [SYNC ...]
                        Provide a list of customer project names to sync with
                        Keystone server
  -i, --dbimport        Only import customer DB. Do not sync Keystone projects
  -c, --cleanup         Delete Keystone projects that were created from
                        customer DB file
  -d, --debug           increase output verbosity
```

### Debug
Running with --debug flag will print debug level messages on the terminal session as well in the log file.
