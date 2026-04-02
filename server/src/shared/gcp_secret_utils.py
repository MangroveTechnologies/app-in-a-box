"""GCP Secret Manager utilities."""
import json
import sys
from typing import Optional

from google.api_core import exceptions as google_exceptions
from google.cloud import secretmanager


class SecretUtils:
    @staticmethod
    def get_secret(
        project_id: str,
        secret_id: str,
        secret_property: str,
        version_id: str = "latest",
    ) -> Optional[str]:
        if not secret_id or not secret_property:
            print("Secret ID or property not supplied.")
            sys.exit(1)

        try:
            client = secretmanager.SecretManagerServiceClient()
            if not project_id:
                print("GCP project id not supplied.")
                sys.exit(1)

            name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
            response = client.access_secret_version(request={"name": name})
            payload = response.payload.data.decode("UTF-8")
            return json.loads(payload)[secret_property]

        except google_exceptions.NotFound:
            print(f"Secret '{secret_id}' not found in project '{project_id}'.")
            sys.exit(1)
        except Exception as e:
            print(f"Error accessing secret {secret_id}: {e}.")
            sys.exit(1)
