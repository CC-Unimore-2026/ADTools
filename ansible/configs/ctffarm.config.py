import os

CONFIG = {
    "DEBUG": os.getenv("DEBUG") == "1",
    "TEAMS": {f"Team #{i}": f"10.60.{i}.1" for i in range(0, 40)},
    "FLAG_FORMAT": r"[A-Z0-9]{31}=",
    "SYSTEM_PROTOCOL": "ructf_http",
    "SYSTEM_URL": "http://10.10.10.10/flags",
    "SYSTEM_TOKEN": "***",
    # The server will submit not more than SUBMIT_FLAG_LIMIT flags
    # every SUBMIT_PERIOD seconds. Flags received more than
    # FLAG_LIFETIME seconds ago will be skipped.
    # You can safely edit these, they won't get overwritten by
    # Ansible.
    "SUBMIT_FLAG_LIMIT": 100,
    "SUBMIT_PERIOD": 2,
    "FLAG_LIFETIME": 5 * 60,
    "SERVER_PASSWORD": "***",
    # For all time-related operations
    # This can be safely edited, it won't get overwritten by Ansible.
    "TIMEZONE": "Europe/Rome",
}
