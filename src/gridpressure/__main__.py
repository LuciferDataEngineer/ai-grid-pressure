import logging

from gridpressure.definitions import defs


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    result = defs.get_implicit_global_asset_job_def().execute_in_process()
    if not result.success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
