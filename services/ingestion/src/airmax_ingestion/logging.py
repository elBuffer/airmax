import json
import logging


def log(event: str, **fields) -> None:
    logging.getLogger("airmax").info(
        json.dumps({"event": event, **fields}, default=str)
    )
