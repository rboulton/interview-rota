# Interview Rota

Code for assigning interviewers to slots for running interviews.

## Getting it running

Needs python 2.  On a mac, with homebrew.

```
$ brew install pyenv-virtualenv
$ virtualenv ENV
$ . ENV/bin/activate
$ pip install -r requirements.txt
```

Download the "people on interview rota" spreadsheet and put in data/interviewers.csv

The code needs access to the google calendar API for reading and writing.  To
set this up: you need to download a client secret file, and set the
CLIENT_SECRET_FILE environment variable to point to it.

To generate a client secret file, you will need a google project, which is
authorised to use the appropriate APIs, and to generate an OAuth client ID for
it, of application type "other".  You can use
https://console.developers.google.com/ to create such a project.  Give it
access to the google calendar API, and then create an OAuth 2.0 client ID file,
and save it to your local machine.

```
$ CLIENT_SECRET_FILE=path/to/client-secrets.json INTERVIEWERS_CSV=data/interviewers.csv ./bin/allocate
```

This will do an Oauth challenge, and then output an environment variable to be
supplied to future runs of ./bin/allocate, which will then be able to contact
google calendar.
