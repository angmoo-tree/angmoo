"""Pinned Windows server resources; no services, cluster or user data changes."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]


def utf8_manifest(existing=None):
    """Set the native process ACP without changing the machine's locale."""
    asm='urn:schemas-microsoft-com:asm.v1'
    application_ns='urn:schemas-microsoft-com:asm.v3'
    setting_ns='http://schemas.microsoft.com/SMI/2019/WindowsSettings'
    ET.register_namespace('',asm)
    ET.register_namespace('asmv3',application_ns)
    root=ET.fromstring(existing) if existing else ET.Element('{'+asm+'}assembly',{'manifestVersion':'1.0'})
    application=root.find('{'+application_ns+'}application')
    if application is None:application=ET.SubElement(root,'{'+application_ns+'}application')
    settings=application.find('{'+application_ns+'}windowsSettings')
    if settings is None:settings=ET.SubElement(application,'{'+application_ns+'}windowsSettings')
    active=settings.find('{'+setting_ns+'}activeCodePage')
    if active is None:active=ET.SubElement(settings,'{'+setting_ns+'}activeCodePage')
    active.text='UTF-8'
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)


def set_utf8_code_page(output,cache):
    # pefile is a Windows build dependency of the pinned PyInstaller toolchain.
    # Preserve existing manifest settings rather than replacing trust/DPI data.
    import pefile
    sdk=Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Windows Kits/10/bin'
    candidates=sorted(sdk.glob('10.*/x64/mt.exe'),reverse=True)
    if not candidates:raise ValueError('windows_postgresql_manifest_tool_required')
    def manifests(path):
        with pefile.PE(str(path)) as pe:
            return [pe.get_data(lang.data.struct.OffsetToData,lang.data.struct.Size)
                for resource in getattr(getattr(pe,'DIRECTORY_ENTRY_RESOURCE',None),'entries',[])
                if resource.id==24 for item in resource.directory.entries for lang in item.directory.entries]
    records={}
    for executable in sorted((output/'bin').glob('*.exe')):
        original=manifests(executable)
        if len(original)>1:raise ValueError('windows_postgresql_manifest_ambiguous')
        manifest=cache/'postgresql-utf8.manifest'
        manifest.write_bytes(utf8_manifest(original[0] if original else None))
        subprocess.run([str(candidates[0]),'-nologo','-manifest',str(manifest),
            '-outputresource:'+str(executable)+';#1'],check=True,capture_output=True,timeout=30)
        written=manifests(executable)
        active=(ET.fromstring(written[0]).find('.//{http://schemas.microsoft.com/SMI/2019/WindowsSettings}activeCodePage')
                if len(written)==1 else None)
        if active is None or active.text!='UTF-8':
            raise ValueError('windows_postgresql_utf8_manifest_verification_failed')
        records[executable.name]={'upstream_manifest_preserved':bool(original),'active_code_page':'UTF-8'}
    if not records:raise ValueError('windows_postgresql_executables_missing')
    return records


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def fetch(url,path,digest):
    if not path.exists():
        with urllib.request.urlopen(url,timeout=90) as response,path.open('xb') as out:shutil.copyfileobj(response,out)
    if sha(path)!=digest:raise ValueError('windows_postgresql_download_hash_mismatch')


def build(output,cache,vcvars=None):
    output,cache=Path(output).absolute(),Path(cache).absolute()
    if os.name!='nt':raise ValueError('windows_postgresql_host_required')
    if any(p.is_symlink() or p.is_junction() for p in (output,cache,*output.parents,*cache.parents)):
        raise ValueError('windows_postgresql_path_link')
    lock=json.loads((ROOT/'scripts/windows-postgresql.lock.json').read_text())
    cache.mkdir(parents=True,exist_ok=True)
    manifest=output/'angmoo-resources.json'
    if manifest.exists():
        from sys import path
        path.insert(0,str(ROOT/'backend'))
        # Reusing a bundle is allowed only if every recorded resource matches.
        value=json.loads(manifest.read_text())
        if (value.get('recipe_lock_sha256')!=sha(ROOT/'scripts/windows-postgresql.lock.json')
            or value.get('recipe_code_sha256')!=sha(Path(__file__))):raise ValueError('windows_postgresql_existing_recipe_mismatch')
        if any(sha(output/name)!=digest for name,digest in value['files'].items()):raise ValueError('windows_postgresql_existing_hash_mismatch')
        return value
    if output.exists() and any(output.iterdir()):raise ValueError('windows_postgresql_output_not_empty')
    output.mkdir(parents=True,exist_ok=True)
    pg=cache/'postgresql-17.11-1-windows-x64-binaries.zip'
    vector=cache/'pgvector-0.8.7.zip'
    fetch(lock['postgresql_url'],pg,lock['postgresql_sha256'])
    fetch(lock['pgvector_url'],vector,lock['pgvector_sha256'])
    with zipfile.ZipFile(pg) as archive:
        for item in archive.infolist():
            p=PurePosixPath(item.filename)
            if p.is_absolute() or '..' in p.parts:raise ValueError('windows_postgresql_archive_path')
            if item.is_dir() or len(p.parts)<2 or p.parts[0]!='pgsql':continue
            relative=Path(*p.parts[1:])
            if relative.parts[0] not in {'bin','lib','share','include','server_license.txt','commandlinetools_3rd_party_licenses.txt'}:continue
            target=output/relative;target.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(item) as source,target.open('xb') as out:shutil.copyfileobj(source,out)
    source=cache/'pgvector-0.8.7'
    if not source.exists():
        with zipfile.ZipFile(vector) as archive:
            for item in archive.infolist():
                p=PurePosixPath(item.filename)
                if p.is_absolute() or '..' in p.parts or p.parts[0]!='pgvector-0.8.7':raise ValueError('pgvector_archive_path')
            archive.extractall(cache)
    if vcvars is None:
        vswhere=Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Microsoft Visual Studio/Installer/vswhere.exe'
        found=subprocess.check_output([str(vswhere),'-latest','-products','*','-requires','Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath'],text=True).strip()
        vcvars=Path(found)/'VC/Auxiliary/Build/vcvars64.bat'
    if not Path(vcvars).is_file():raise ValueError('windows_postgresql_compiler_required')
    # Batch syntax is restricted to trusted absolute paths; reject expansion
    # metacharacters before writing the single-shell build recipe.
    if any(any(c in str(p) for c in '\r\n%&|<>^"') for p in (vcvars,output,source)):
        raise ValueError('windows_postgresql_build_path_invalid')
    script=cache/'build-pgvector.cmd'
    script.write_text('@call "'+str(vcvars)+'"\n@if errorlevel 1 exit /b 1\n@set "PGROOT='+str(output)+'"\n@cd /d "'+str(source)+'"\n@nmake /F Makefile.win\n@if errorlevel 1 exit /b 1\n@nmake /F Makefile.win install\n',encoding='utf-8')
    with (cache/'build-pgvector.log').open('wb') as log:
        subprocess.run(['cmd','/d','/c',str(script)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
    shutil.copyfile(source/'LICENSE',output/'pgvector-LICENSE.txt')
    code_pages=set_utf8_code_page(output,cache)
    # Headers are build-time input, not a runtime dependency.
    headers=(output/'include').resolve()
    if not headers.is_relative_to(output.resolve()) or headers==output.resolve():raise ValueError('windows_postgresql_cleanup_path_invalid')
    shutil.rmtree(headers)
    files={str(p.relative_to(output)).replace('\\','/'):sha(p) for p in sorted(output.rglob('*')) if p.is_file()}
    value={'schema':'angmoo-postgresql-resources.v1','postgresql':lock['postgresql'],'pgvector':lock['pgvector'],
        'platform':'windows-x64','recipe_lock_sha256':sha(ROOT/'scripts/windows-postgresql.lock.json'),
        'recipe_code_sha256':sha(Path(__file__)),'process_code_pages':code_pages,'files':files,
        'sources':{key:lock[key] for key in ('postgresql_url','postgresql_sha256','pgvector_url','pgvector_sha256')}}
    manifest.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    return value


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--vcvars',type=Path)
    args=parser.parse_args();value=build(args.output,args.cache,args.vcvars)
    print(json.dumps({key:value[key] for key in ('schema','postgresql','pgvector','recipe_lock_sha256')}))
