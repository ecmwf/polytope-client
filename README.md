# polytope-client

This repository contains the source code and documentation of a Polytope client implemented in Python, which communicates with the RESTful API exposed by a Polytope server.

:warning: This project is BETA and will be experimental for the forseable future. Interfaces and functionality are likely to change, and the project itself may be scrapped. DO NOT use this software in any project/software that is operational.

&nbsp;
## 1. Installation

Install the Polytope client with python3 (>= 3.6) and pip as follows:
```bash
python3 -m pip install --upgrade git+https://github.com/ecmwf-projects/polytope-client.git@master
# make sure the installed polytope executable is added to your PATH if willing to use the CLI
```

Or from PyPi (not yet available):
```bash
python3 -m pip install polytope-client
```

&nbsp;
## 2. Account creation

In order to access the API, you must first obtain an account for the Polytope server you intend to operate with. Ask the server administrator.

&nbsp;
## 3. API example

If using a username and password as credentials (as opposed to EmailKey or Bearer credentials, also supported by Polytope) it is recommended to set your username and password as environment variables before starting python:
```bash
export POLYTOPE_USERNAME=<your_account_name>
export POLYTOPE_PASSWORD=<your_account_password>
```

Start a python3 session to use the API.
```python
#!/usr/bin/env python3

from polytope.api import Client

help(Client)

# Instantiate and configure the client
# If using EmailKey or Bearer credentials, you can specify them in the Client constructor
# You can disregard these parameters if you have specified your credentials via environment 
# variables or configuration file
c = Client(user_email = 'johndoe@ecmwf.int',
           user_key = '4j3s3d34n4sn335jacf3n3d4f4g61635')

# List the available collections to retrieve from
c.list_collections()

request = {
    'stream': 'oper',
    'levtype': 'sfc',
    'param': '165.128/166.128/167.128',
    'step': '0',
    'time': '00/06/12/18',
    'date': '20150323',
    'type': 'an',
    'class': 'od',
    'expver': '0001',
    'domain': 'g'
}

# Retrieve data
c.retrieve('mars', request, 'output_api.grib')

# List the active requests
ids = c.list_requests()

# Revoke a request
c.revoke(ids[0])

# Append to an existing file
c.retrieve('mars', request, 'output_api.grib', append = True)

# Multiple retrieval
c.retrieve('mars', [request] * 3, 'output_api.grib')

# Asynchronous retrieval
r = c.retrieve('mars', request, 'output_api.grib',
               asynchronous = True)
r[0].describe()
r[0].download()

# Pointer retrieval
r = c.retrieve('mars', request, pointer = True)
print(r[0])

# Archive data from local file
c.archive('archive-collection', request, 'output_api.grib')

# Archive data from URL
c.archive('archive-collection', request, r[0]['location'])

# Revoke all requests
c.revoke('all')
```

&nbsp;
## 4. CLI example

You can check the documentation of the CLI as follows.
```bash
polytope -h
```

```bash
# if using EmailKey or Bearer credentials, provide them as follows:
export POLYTOPE_USER_EMAIL=johndoe@ecmwf.int
export POLYTOPE_USER_KEY=4j3s3d34n4sn335jacf3n3d4f4g61635

# if using plain username and password as credentials, provide them as follows:
export POLYTOPE_USERNAME=<your_account_name>
export POLYTOPE_PASSWORD=<your_account_password>

polytope list config

polytope list credentials

polytope describe user

polytope list collections

polytope retrieve mars -e "stream = oper, \
    levtype = sfc,
    param = 165.128/166.128/167.128,
    dataset = interim,
    step = 0,
    grid = 0.75/0.75,
    time = 00/06/12/18,
    date = 20110323/to/20110324,
    type = an,
    class = od,
    expver = 0001" output_cli.grib

du -sch output_cli.grib

# Or, if you prefer to specify your request in a separate file:

cat > request.yaml <<EOF
{
    'stream' : 'oper',
    'levtype' : 'sfc',
    'param' : '165.128/166.128/167.128',
    'dataset' : 'interim',
    'step' : '0',
    'grid' : '0.75/0.75',
    'time' : '00/06/12/18',
    'date' : '20110323/to/20110324',
    'type' : 'an',
    'class' : 'od',
    'expver' : '0001'
}
EOF

polytope retrieve mars request.yaml output_cli.grib

polytope list requests

polytope revoke 8071048e4a19f5140f0b40548dbddb76

polytope archive archive-collection request.yaml output_cli.grib

polytope revoke all
```

The following dialog shows an overview of the syntax of the CLI:
```bash

# High-level user commands

# global options:
# 
# -c --config-path
# -a --address
# -p --port
# -u --username
# -p --password
# -K --key-path
# -q --quiet
# -v --verbose
# --user-email
# --user-key
# --log-file
# --log-level
# -k --key
# -h --help


polytope set config <key> <value> [--global-opt value ...]

polytope unset config <key> | all [--global opts ...]

polytope list config [--global opts ...]



polytope set credentials <key> [<username>] [--global opts ...]

polytope unset credentials [<username>] [--global opts ...]

polytope list credentials



polytope retrieve <collection_name> <data.yaml> [<output_file>] [-A|--async] 
                            [-m|--max-attempts] [-P|--attempt-period] 
                            [--append] [--pointer] [--global opts ...]

polytope retrieve <collection_name> -e <inline_request> [<output_file>] [-A|--async]
                            [-m|--max-attempts] [-P|--attempt-period] 
                            [--append] [--pointer] [--global opts ...]

example of an inline request:

"stream=oper, type=an, class=ei, dataset = interim, levtype=sfc, param=165.128/166.128/167.128, time=00/06/12/18, date=2014-07-05/to/2014-07-06, step=0, grid=0.75/0.75"



polytope list requests [--global-opts ...]

polytope describe request <request_id> [--global-opts ...]

polytope revoke <request_id>|all [--global-opts ...]



# Low-level power-user commands

polytope login [<username>] [--login-password] [--key-type] [--global-opts ...]

polytope download <request_id> [<output_file>] [-A|--async] [-m|--max-attempts] 
                            [-P|--attempt-period] [--append] [--pointer] 
                            [--global opts ...]

polytope archive <collection_name> <metadata.yaml> <input_url> [-m|--max-attempts] 
                            [-P|--attempt-period] [-A|--async] [--global opts ...]

polytope upload <request_id> <input_url> [-A|--async] [-m|--max-attempts]
                            [-P|--attempt-period] [--global opts ...]
```
