"""Export only server-verified opt-in logs; optionally train without promoting a model."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.db import make_database
from app.security import signing_secret
from app.training import export_training, verify_export


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, help='Existing private output directory')
    parser.add_argument('--train-out', help='Existing private directory for an unpromoted candidate model')
    args = parser.parse_args()
    if not Path(args.out).is_dir() or (args.train_out and not Path(args.train_out).is_dir()):
        parser.error('Output directories must already exist')
    settings = Settings.from_env()
    engine, factory = make_database(settings)
    try:
        with factory() as db:
            secret = signing_secret(db, settings.secret)
            if db.bind.dialect.name == 'sqlite':
                from sqlalchemy import text
                db.execute(text('BEGIN IMMEDIATE'))
            data, manifest = export_training(db, secret, args.out)
            verify_export(db, secret, data, manifest)
            db.commit()
        if args.train_out:
            # Recheck current consent and hold grant-user locks through the blocking worker.
            with factory() as db:
                if db.bind.dialect.name == 'sqlite':
                    from sqlalchemy import text
                    db.execute(text('BEGIN IMMEDIATE'))
                verify_export(db, secret, data, manifest)
                from app.adaptation import train_on_opt_in_csv
                train_on_opt_in_csv(data, manifest, args.train_out)
                db.commit()
        print(f'Exported {data} and {manifest}. No candidate is automatically promoted.')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
