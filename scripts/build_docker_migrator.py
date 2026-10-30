"""Package the stdlib Docker host adapter from one immutable product source."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def build(output,work,source):
    if len(source)!=40 or any(c not in '0123456789abcdef' for c in source):raise ValueError('migration_tool_source_invalid')
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if source!=actual:raise ValueError('migration_tool_checkout_mismatch')
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ROOT,text=True).strip():
        raise ValueError('migration_tool_clean_checkout_required')
    output,work=Path(output),Path(work)
    output.mkdir(parents=True,exist_ok=True);work.mkdir(parents=True,exist_ok=True)
    text=(ROOT/'launcher/migrate/docker_migrate.py').read_text(encoding='utf-8')
    marker='BUILD_SOURCE = None  # Release packaging binds this launcher to product source S.'
    if text.count(marker)!=1:raise ValueError('migration_tool_template_invalid')
    data=text.replace(marker,'BUILD_SOURCE = '+repr(source)).encode('utf-8')
    target=output/'angmoo-migrate.py';target.write_bytes(data)
    if os.name!='nt':raise ValueError('migration_executable_requires_windows_builder')
    import PyInstaller
    if PyInstaller.__version__!='6.16.0':raise ValueError('migration_packager_version_mismatch')
    subprocess.run([sys.executable,'-m','PyInstaller','--onefile','--console','--noupx','--noconfirm','--clean',
        '--name','angmoo-migrate','--distpath',str(output),'--workpath',str(work/'build'),'--specpath',str(work),str(target)],check=True)
    assets={name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in ('angmoo-migrate.exe','angmoo-migrate.py')}
    value={'schema':'angmoo-migration-tools.v1','source_sha':source,'source_version':'0.1.3','target_version':'0.1.4',
        'files':assets,'canonical_converter':'target backend image at the same source','pyinstaller':'6.16.0'}
    (output/'angmoo-migration-tools.json').write_text(json.dumps(value,indent=2)+'\n')
    return value


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
    p.add_argument('--source',default=None);a=p.parse_args()
    source=a.source or subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    print(json.dumps(build(a.output,a.work,source)))
