
import sys

from loguru import logger


def get_message_format(with_mp: bool = False):
    def level_aware_format(record):
        # see: https://loguru.readthedocs.io/en/stable/api/logger.html#record
        level_icon = "<lvl>{level.icon} {level:<7}</lvl>"
        separator = " <c>|></c> "
        msg_format = level_icon + separator
        if record.get("level").name == "DEBUG":
            msg_format += "<g>({function})</g> {message}"
        elif record.get("level").name == "WARNING":
            level_icon = "<lvl>{level.icon}  {level:<7}</lvl>"
            msg_format = level_icon + separator + "<g>({function})</g> <y>{message}</y>"
        elif record.get("level").name == "SUCCESS":
            msg_format += "<g>{message}</g>"
        elif record.get("level").name == "INFO":
            level_icon = "<lvl>{level.icon}  {level:<7}</lvl>"
            msg_format = level_icon + separator + "{message}"
        else:
            msg_format += "{message}"
        return msg_format + "\n{exception}"
    return level_aware_format


def enable_logger(level="INFO", **kwargs):
    global logger
    logger.remove()  # Remove the default handler.
    default_kwargs = dict(  # noqa: C408
        sink=sys.stderr,
        format=get_message_format(),
        colorize=True,
        level=level
    )
    logger.add(**(default_kwargs | (kwargs or {})))
    logger = logger.opt(colors=True)
    logger.enable("__main__")
    logger.enable("caelus")


def disable_logger():
    logger.disable("__main__")
    logger.disable("caelus")
