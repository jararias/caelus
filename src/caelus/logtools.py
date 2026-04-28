
import sys

from loguru import logger


def get_message_format(with_mp: bool = False):
    def level_aware_format(record):
        # see: https://loguru.readthedocs.io/en/stable/api/logger.html#record
        level_icon = "<lvl>{level.icon} {level:<7}</lvl>"
        separator = " <c>|></c> "
        process_info = "<magenta>{process.name:<12}</magenta> " if with_mp else ""
        msg_format = level_icon + process_info + separator
        if record.get("level").name == "DEBUG":
            msg_format += "<g>({function})</g> {message}"
        elif record.get("level").name == "WARNING":
            level_icon = "<lvl>{level.icon}  {level:<7}</lvl>"
            msg_format = level_icon + process_info + separator + "<g>({function})</g> <y>{message}</y>"
        elif record.get("level").name == "SUCCESS":
            msg_format += "<g>{message}</g>"
        elif record.get("level").name == "INFO":
            level_icon = "<lvl>{level.icon}  {level:<7}</lvl>"
            msg_format = level_icon + process_info + separator + "{message}"
        else:
            msg_format += "{message}"
        return msg_format + "\n{exception}"
    return level_aware_format


def filtrar_logs(filtros: list[str] | None = None):
    def filtro(record):
        if any(record["name"].startswith(name) for name in filtros or []):
            return record["level"].no >= logger.level("ERROR").no  # only pass if is an ERROR or more severe
        return True  # any other will pass through
    return filtro

def enable_logger(name: str | None = None, with_mp: bool = False, filtros: list[str] | None = None, **kwargs):
    global logger
    logger.remove()  # Remove the default handler.
    default_kwargs = dict(  # noqa: C408
        sink=sys.stderr,
        level="INFO",
        format=get_message_format(with_mp=with_mp),
        colorize=True,
        enqueue=with_mp,
        filter=filtrar_logs(filtros or []),
    )
    logger.add(**(default_kwargs | (kwargs or {})))
    logger = logger.opt(colors=True)
    logger.enable(name or "caelus")


def disable_logger(name: str | None = None):
    logger.disable(name or "caelus")