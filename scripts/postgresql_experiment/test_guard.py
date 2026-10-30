import json,os,tempfile,unittest
from pathlib import Path
from guard import GuardError,MARKER,RUN_ID,SOURCE_SHA,owned_path,require_dsn,require_local_image,write_private_once

class Boundaries(unittest.TestCase):
    def test_private_secret_publication_keeps_the_first_value(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'fixture'
            write_private_once(path,'synthetic first value')
            if os.name!='nt':self.assertEqual(path.stat().st_mode&0o777,0o600)
            with self.assertRaises(FileExistsError):write_private_once(path,'different value')
            self.assertEqual(path.read_text(),'synthetic first value')
            self.assertEqual(list(Path(d).iterdir()),[path])

    def test_foreign_paths_and_owner_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(GuardError):owned_path(root,'pgdata')
            (root/MARKER).write_text(json.dumps({'run_id':RUN_ID,'source_sha':SOURCE_SHA}))
            self.assertEqual(owned_path(root,'pgdata'),root/'pgdata')
            for value in ['../original','../../data',str(root.parent/'original')]:
                with self.assertRaises(GuardError):owned_path(root,value)
            (root/MARKER).write_text(json.dumps({'run_id':'other','source_sha':SOURCE_SHA}))
            with self.assertRaises(GuardError):owned_path(root,'pgdata')

    def test_dsn_cannot_target_default_or_network_database(self):
        require_dsn('postgresql://angmoo_pg_run01@127.0.0.1:15414/angmoo_pg_run01')
        for dsn in ['postgresql://postgres@localhost:5432/postgres',
                    'postgresql://angmoo_pg_run01@192.168.0.1:15414/angmoo_pg_run01',
                    'sqlite:///original.db',
                    'postgresql://angmoo_pg_run01@127.0.0.1:15414/angmoo']:
            with self.assertRaises(GuardError):require_dsn(dsn)

    def test_official_images_cannot_be_mutated(self):
        require_local_image('angmoo-pg-exp/postgres:17-0.8.7-arm64')
        for name in ['ghcr.io/angmoo-tree/angmoo-backend:0.1.3','postgres:17','angmoo-pg-exp/postgres:latest']:
            with self.assertRaises(GuardError):require_local_image(name)

if __name__=='__main__':unittest.main()
