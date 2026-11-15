"""python -m pipeline run [--district <id> ...]"""
import argparse
import json
import logging
from datetime import date

from pipeline.run import run


def main():
    ap = argparse.ArgumentParser(prog="pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="один цикл конвейера")
    r.add_argument("--district", action="append", help="id района (можно несколько); по умолчанию все")
    r.add_argument("--today", help="дата «сегодня» (YYYY-MM-DD) для воспроизводимого прогона")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.cmd == "run":
        res = run(args.district, date.fromisoformat(args.today) if args.today else None)
        print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
