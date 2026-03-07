"""Application configuration singleton.

Loads per-environment JSON config files from src/config/.
Resolves GCP Secret Manager references using secret:name:property syntax.
Validates all required keys at startup.
"""
import json
import os
import sys

from src.shared.gcp_secret_utils import SecretUtils


class _Config:
    def __init__(self):
        self._raw_config = {}
        self.load_configuration()

    def load_configuration(self):
        environment = os.getenv("ENVIRONMENT") or os.getenv("APP_ENV")
        if not environment:
            print("ENVIRONMENT or APP_ENV is not set.")
            sys.exit(1)
        setattr(self, "ENVIRONMENT", environment)

        configuration_keys = self.get_configuration_keys()
        self.load_config_file()
        gcp_project_id = os.getenv("GCP_PROJECT_ID")
        if not gcp_project_id:
            print("GCP_PROJECT_ID not set. Secret Manager lookups will fail.")

        for key in configuration_keys:
            if key not in self._raw_config:
                print(f"Configuration key {key} missing from config file.")
                sys.exit(1)
            key_value = self.get_key_value(key, gcp_project_id)
            if str(key_value).strip().lower() in {"none", "null"}:
                key_value = None
            setattr(self, key, key_value)

    @staticmethod
    def get_configuration_keys() -> set:
        try:
            config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
            keys_path = os.path.join(config_dir, "configuration-keys.json")
            with open(keys_path, "r") as f:
                keys_list = json.load(f)
                return set(keys_list["required_keys"])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Failed to load configuration-keys.json: {e}")
            sys.exit(1)

    def load_config_file(self):
        environment = os.getenv("ENVIRONMENT") or os.getenv("APP_ENV")
        filename = f"{environment}-config.json"
        try:
            config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
            file_path = os.path.join(config_dir, filename)

            if not os.path.exists(file_path):
                print(f"Config file not found: {file_path}")
                sys.exit(1)

            with open(file_path, "r") as f:
                config_data = json.load(f)
            self._raw_config.update(config_data)

        except Exception as e:
            print(f"Error loading {filename}: {e}")
            sys.exit(1)

    def get_key_value(self, key: str, project_id: str) -> str:
        value = self._raw_config.get(key)
        str_val = str(value)
        if str_val.startswith("secret:"):
            parts = str_val.split(":")
            secret_id = parts[1]
            secret_property = parts[2]
            value = SecretUtils.get_secret(project_id, secret_id, secret_property)
        return value


app_config = _Config()
