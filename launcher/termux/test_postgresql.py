import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import angmoo
import postgres_host
import processes
import migrate
from types import SimpleNamespace
from contextlib import redirect_stdout
from payload import services_for


class PostgreSQLHostTests(unittest.TestCase):
    def test_resume_refuses_changed_source_or_image_before_source_stop(self):
        from copy import deepcopy
        manifest={'version':'0.1.4','source_sha':'a'*40,'images':[
            {'service':s,'platform':'linux/arm64','manifest_digest':'sha256:'+'b'*64,'config_digest':'sha256:'+'c'*64}
            for s in ('backend','frontend','postgres')]}
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory)/'source';target=home.with_name(home.name+'-postgresql')
            home.mkdir();target.mkdir();(target/'installation.json').write_text('{}')
            args=SimpleNamespace(rollback=False,language='en',candidate_manifest=Path('candidate.json'),manifest=None,release=None)
            for fault in ('source','image'):
                requested=deepcopy(manifest)
                if fault=='source':requested['source_sha']='d'*40
                else:requested['images'][0]['config_digest']='sha256:'+'e'*64
                with patch.object(angmoo,'installation',return_value={'manifest':manifest}),patch.object(angmoo,'stop') as stop,patch.object(migrate,'read_manifest',return_value=requested):
                    with self.assertRaisesRegex(ValueError,'resume_target_changed'):migrate.run(home,args)
                    stop.assert_not_called()
            with patch.object(migrate,'read_manifest',return_value=manifest):
                migrate.require_resume_target({'manifest':manifest},args)

    def test_rollback_reports_sqlite_selection_in_both_languages_and_keeps_target(self):
        for language in ('en','ko'):
            with tempfile.TemporaryDirectory() as directory:
                home=Path(directory)/'source';target=home.with_name(home.name+'-postgresql')
                home.mkdir();target.mkdir();(target/'preserved-data').write_bytes(b'new-pg-data')
                (home/'selection.json').write_text(json.dumps({'schema':'angmoo-termux-selection.v1','target_home':str(target)}))
                output=io.StringIO()
                with patch.object(angmoo,'stop') as stop,redirect_stdout(output):
                    migrate.run(home,SimpleNamespace(rollback=True,language=language),ask=lambda _:'yes')
                stop.assert_called_once_with(target)
                self.assertEqual(migrate.selected(home),home)
                self.assertIn('0.1.3',output.getvalue())
                self.assertEqual((target/'preserved-data').read_bytes(),b'new-pg-data')
    def test_initialized_cluster_cannot_regenerate_missing_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory);postgres_host.prepare(home)
            (home/'postgresql-data/PG_VERSION').write_text('17')
            (home/'credentials/runtime-password').unlink()
            with self.assertRaisesRegex(ValueError,'credentials_missing'):postgres_host.prepare(home)
            self.assertFalse((home/'credentials/runtime-password').exists())

    def test_short_ipc_is_private_bound_and_passed_to_isolated_guest(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory)/('long-home-'*15);home.mkdir()
            config={'home':str(home),'proot_wrapper':str(home/'tools/proot-wrapper'),'containers':{'postgres':'pg'}}
            with patch.object(postgres_host.Path,'home',return_value=Path(directory)):
                short=postgres_host.temporary_directory(config)
                self.assertEqual(json.loads((short/'owner.json').read_text())['home'],str(home.resolve()))
                args=postgres_host.options('proot-distro',config,'postgres')
                self.assertIn('PROOT_DONT_SHARE_LIBANDROID_SHMEM=1',args)
                self.assertIn('PROOT_TMP_DIR='+str(short),args)
                (short/'owner.json').write_text('{}')
                with self.assertRaisesRegex(ValueError,'owner_mismatch'):postgres_host.temporary_directory(config)

    def test_version_selects_complete_service_set_and_health_contract(self):
        self.assertEqual(services_for('0.1.3'),('backend','frontend'))
        self.assertEqual(set(services_for('0.1.4')),{'backend','frontend','postgres'})
        value={'version':'0.1.4','source_sha':'a'*40,'launch_id':'b'*32,'status':'ok','persistence':'postgresql','graph':'ladybug'}
        with patch.object(processes.urllib.request,'urlopen',side_effect=lambda *_a,**_k:io.BytesIO(json.dumps(value).encode())):
            self.assertTrue(processes.probe_ready('http://fixture','a'*40,'b'*32,expected_version='0.1.4',backend=True)['ready'])
            value['persistence']='sqlite'
            self.assertFalse(processes.probe_ready('http://fixture','a'*40,'b'*32,expected_version='0.1.4',backend=True)['ready'])

    def test_credentials_survive_restart_and_are_not_in_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory)
            ports={'postgres':15544,'backend':18144,'frontend':13144}
            first=postgres_host.prepare(home,ports)
            secrets=(home/'credentials/postgres-password').read_text().strip()
            self.assertEqual(first,postgres_host.prepare(home,ports))
            config={'home':str(home),'data_root':str(home/'data'),'ports':ports,
                    'containers':{'postgres':'fixture-postgres','backend':'fixture-backend','frontend':'fixture-frontend'}}
            pg=postgres_host.command('proot-distro',config)
            self.assertIn('15544',pg)
            self.assertNotIn(secrets,' '.join(pg))
            self.assertIn('127.0.0.1:15544',(home/'credentials/owner-dsn').read_text())
            with self.assertRaisesRegex(ValueError,'ports_changed'):postgres_host.prepare(home,{**ports,'postgres':15545})
            with patch.object(angmoo,'is_termux_host',return_value=True):
                backend=angmoo.command('proot-distro',config,'backend','b'*32)
                frontend=angmoo.command('proot-distro',config,'frontend','b'*32)
            self.assertIn('ANGMOO_FRONTEND_ORIGIN=http://127.0.0.1:13144',backend)
            self.assertIn('ANGMOO_API_BASE_URL=http://127.0.0.1:18144',frontend)


if __name__=='__main__':unittest.main()
