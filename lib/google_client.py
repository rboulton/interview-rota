"""Client for accessing google APIs.

"""

from oauth2client import client
from oauth2client import tools
from oauth2client.contrib.dictionary_storage import DictionaryStorage
import base64
import os
import zlib

CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar'
CREDENTIALS_ENV_VAR = "GOOGLE_CREDENTIALS"
CLIENT_SECRET_FILE_ENV_VAR = "CLIENT_SECRET_FILE"


class GoogleAuthentication(object):

    def __init__(self):
        self.storage_dict = {}
        self.storage = DictionaryStorage(self.storage_dict, "creds")

    def credentials_supplied(self):
        return CREDENTIALS_ENV_VAR in os.environ

    def get_credentials(self):
        """Get credentials from environment.

        Returns None if no credentials were supplied or the supplied
        credentials were invalid.

        Otherwise returns an oauth2client Credentials object.
        """
        serialised_creds = os.environ.get(CREDENTIALS_ENV_VAR)
        if serialised_creds:
            self.storage_dict["creds"] = zlib.decompress(base64.decodestring(serialised_creds))
        creds = self.storage.get()

        if creds is None or creds.invalid:
            return None
        return creds

    def initial_auth(self):
        """Run the authorisation flow with Google to make some credentials.

        This should only need to be run once, and requires that a client
        secrets file has been downloaded.
        """
        if CLIENT_SECRET_FILE_ENV_VAR not in os.environ:
            print("""
You need to download a client secret file, and set the
{} environment variable to point to it.

To generate a client secret file, you will need a google project, which is
authorised to use the appropriate APIs, and to generate an OAuth client ID for
it, of application type "other".  You can use
https://console.developers.google.com/ to create such a project. 
""".format(CLIENT_SECRET_FILE_ENV_VAR))
            return
        client_secrets_file = os.environ[CLIENT_SECRET_FILE_ENV_VAR]
        flow = client.flow_from_clientsecrets(client_secrets_file, [
            CALENDAR_SCOPE,
        ])
        creds = tools.run_flow(flow, self.storage, None)
        return not(creds is None or creds.invalid)

    def display_credentials(self):
        print("""
Persistent credentials have been generated.  These allow access to the google
account without further authorisation.  Keep them secure, and revoke them in
the google dashboard when they're no longer needed or if there is a risk that
they may have leaked.

Please now delete the supplied client secrets file.
""")

        print("{}='{}'".format(CREDENTIALS_ENV_VAR,
            base64.encodestring(zlib.compress(self.storage_dict["creds"],
                9)).replace("\n", ""),
        ))
