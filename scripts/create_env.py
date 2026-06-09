
import getpass
import os
import sys
from pathlib import Path

from loguru import logger
from pykeepass import PyKeePass

logger.remove()  # Remove the default handler.
logger.add(
    sink=sys.stderr,
    level="INFO",
    format="<lvl>{level}:</lvl> <lvl>{message}</lvl>",
    colorize=True)
logger = logger.opt(colors=True)


logger.disable(__name__)


def get_file_path_from_env(env_var: str) -> Path:
    if not (env_var_file := os.environ.get(env_var)):
        logger.error(f"'{env_var}' not set")
        exit(1)

    if not (env_var_file := Path(env_var_file).expanduser()).is_file():
        logger.error(f"'{env_var_file}' does not exist")
        exit(1)

    return env_var_file


def push_entry_token(entry, token_name):
    with open(".env", "a") as f:
        f.write(f"{token_name}={entry.password}\n")


if __name__ == "__main__":

    KEEPASS_DB_FILE = get_file_path_from_env("KEEPASS_DB_FILE")
    logger.info(f"Using Keepass DB <blue>{KEEPASS_DB_FILE}</blue>")

    KEEPASS_KEY_FILE = get_file_path_from_env("KEEPASS_KEY_FILE")
    logger.info(f"Using Keepass key file <blue>{KEEPASS_KEY_FILE}</blue>")

    master_password = getpass.getpass("Type DB master password: ")

    with PyKeePass(KEEPASS_DB_FILE, password=master_password, keyfile=KEEPASS_KEY_FILE) as kp:

        if not (entries := kp.find_entries(title="pypi")):
            logger.error("Entry 'pypi' not found in the Keepass database.")
            exit(1)
        push_entry_token(entries[0], "UV_PUBLISH_TOKEN")

        if not (entries := kp.find_entries(title="test-pypi")):
            logger.error("Entry 'test-pypi' not found in the Keepass database. Removing .env file.")
            Path(".env").unlink(missing_ok=True)
            exit(1)
        push_entry_token(entries[0], "UV_PUBLISH_TEST_TOKEN")

    if not Path(".env").is_file():
        logger.error("Failed to create .env file.")
        exit(1)
    logger.success("Environment file <blue>.env</blue> created successfully.")