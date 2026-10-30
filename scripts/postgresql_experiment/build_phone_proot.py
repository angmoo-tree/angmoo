"""Build an experiment-local PRoot; never install over Termux's package."""
import hashlib,json,os,pathlib,subprocess,urllib.request,zipfile
from guard import require_owned_root,owned_path,RUN_ID
ROOT=pathlib.Path.home()/'angmoo-pg-experiments/20261027-run01'
VERSION='5.1.107.101'
SHA='a66743f50c7b0bac1913b83bf55e139d679c80a0ca2808eec76432a65640017f'
URL=f'https://github.com/termux/proot/archive/v{VERSION}.zip'

def build():
    root=require_owned_root(ROOT)
    sources=owned_path(root,'sources');sources.mkdir(exist_ok=True,mode=0o700)
    tools=owned_path(root,'tools');tools.mkdir(exist_ok=True,mode=0o700)
    archive=sources/f'proot-{VERSION}.zip'
    if not archive.exists():
        with urllib.request.urlopen(URL,timeout=45) as r,archive.open('xb') as f:
            while block:=r.read(1024*1024):f.write(block)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=SHA:raise ValueError('proot_source_digest_mismatch')
    source=sources/f'proot-{VERSION}'
    if not source.exists():
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                p=pathlib.PurePosixPath(name)
                if p.is_absolute() or '..' in p.parts or p.parts[0]!=f'proot-{VERSION}':raise ValueError('proot_archive_path')
            z.extractall(sources)
    file=source/'src/extension/sysvipc/sysvipc_shm.c'
    old='execl("/proc/self/exe", "proot", "--shm-helper", NULL);'
    new='''/* Angmoo experiment: Play Store Termux runs via linker64. */
                const char *self_exe = getenv("ANGMOO_PROOT_SELF_EXE");
                if (self_exe != NULL && self_exe[0] == '/') {
                    execl("/system/bin/linker64", "linker64", self_exe, "--shm-helper", NULL);
                } else {
                    execl("/proc/self/exe", "proot", "--shm-helper", NULL);
                }'''
    text=file.read_text()
    if new not in text:
        assert text.count(old)==1
        file.write_text(text.replace(old,new))
    # Match the Play Store package's official loader integration. Android only
    # executes this loader from the already installed APK's native library dir.
    enter=source/'src/execve/enter.c'
    content=enter.read_text()
    for before,after in [
        ('getenv("PROOT_LOADER_32") ?: PROOT_UNBUNDLE_LOADER "/loader32"','PROOT_UNBUNDLE_LOADER "/libproot-loader32.so"'),
        ('getenv("PROOT_LOADER") ?: PROOT_UNBUNDLE_LOADER "/loader"','PROOT_UNBUNDLE_LOADER "/libproot-loader.so"')]:
        if after not in content:
            assert content.count(before)==1
            content=content.replace(before,after)
    enter.write_text(content)
    loader=pathlib.Path('/data/data/com.termux/files/applib/libproot-loader.so')
    assert loader.is_file()
    # zip archives do not preserve executable mode; upstream make invokes scripts.
    for path in source.rglob('*.sh'):path.chmod(0o700)
    args=['make','-B','-C',str(source/'src'),'-j2','PROOT_WITH_LIBANDROID_SHMEM=true','CC=clang',
          'PROOT_UNBUNDLE_LOADER=/data/data/com.termux/files/applib',
          'CPPFLAGS=-D_FILE_OFFSET_BITS=64 -D_GNU_SOURCE -I. -DARG_MAX=131072 -DVERSION=\\"5.1.107.101-angmoo-shm1\\"']
    result=subprocess.run(args,capture_output=True,text=True,timeout=240)
    record={'run_id':RUN_ID,'source_url':URL,'source_sha256':SHA,'version':VERSION,
       'patch':'SysV helper self-exec through Android linker with explicit guarded experiment binary path',
       'patched_source_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
       'loader_patch_source':'https://github.com/termux-play-store/termux-packages/blob/main/packages/proot/src-execve-enter.c.patch',
       'loader_sha256':hashlib.sha256(loader.read_bytes()).hexdigest(),
       'patched_execve_sha256':hashlib.sha256(enter.read_bytes()).hexdigest(),
       'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
    if result.returncode==0:
        target=tools/'proot-playstore'
        assert not target.exists()
        target.write_bytes((source/'src/proot').read_bytes());target.chmod(0o700)
        record['binary_sha256']=hashlib.sha256(target.read_bytes()).hexdigest();record['binary']=str(target)
    (root/'records/proot-build.json').write_text(json.dumps(record,indent=2)+'\n')
    return record

if __name__=='__main__':print(json.dumps(build(),indent=2))
