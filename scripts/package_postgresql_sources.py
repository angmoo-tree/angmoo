"""Ship exact LGPL library source and notices beside PostgreSQL releases."""
import argparse,hashlib,json,shutil,tomllib,urllib.request,zipfile
from importlib.metadata import distribution
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def package(output,cache):
    output,cache=Path(output),Path(cache);output.parent.mkdir(parents=True,exist_ok=True);cache.mkdir(parents=True,exist_ok=True)
    lock=json.loads((ROOT/'security/psycopg-source-lock.json').read_text())
    pool=next(p for p in tomllib.loads((ROOT/'backend/uv.lock').read_text())['package'] if p['name']=='psycopg-pool')
    entries=[('psycopg-3.3.6-source.zip',lock['url'],lock['sha256']),
        ('psycopg-pool-'+pool['version']+'-source.tar.gz',pool['sdist']['url'],pool['sdist']['hash'].removeprefix('sha256:'))]
    files={}
    for name,url,digest in entries:
        path=cache/name
        if not path.exists():
            with urllib.request.urlopen(url,timeout=90) as incoming,path.open('xb') as out:shutil.copyfileobj(incoming,out)
        if hashlib.file_digest(path.open('rb'),'sha256').hexdigest()!=digest:raise ValueError('postgresql_source_digest_mismatch')
        files[name]=path.read_bytes()
    for name,version in (('psycopg','3.3.6'),('psycopg-binary','3.3.6'),('psycopg-pool','3.3.3')):
        dist=distribution(name)
        if dist.version!=version:raise ValueError('postgresql_license_version_mismatch')
        licenses=[f for f in dist.files if '/licenses/' in str(f)]
        if not licenses:raise ValueError('postgresql_dependency_license_missing')
        for path in licenses:files['licenses/'+name+'-'+version+'/'+Path(path).name]=dist.locate_file(path).read_bytes()
    for name,relative in [('GPL-3.0.txt','LICENSE'),('REBUILD.md','docs/operations/postgresql-dependencies.md'),
        ('psycopg-source-lock.json','security/psycopg-source-lock.json')]:files[name]=(ROOT/relative).read_bytes()
    files['SOURCES.json']=(json.dumps({'schema':'angmoo-postgresql-sources.v1','sources':[
        {'name':name,'url':url,'sha256':digest} for name,url,digest in entries]},indent=2)+'\n').encode()
    with zipfile.ZipFile(output,'w') as archive:
        for name,body in sorted(files.items()):
            item=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));item.create_system=3;item.external_attr=0o100644<<16
            item.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(item,body,compresslevel=9)
    return {'schema':'angmoo-postgresql-source-bundle.v1','sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'files':len(files)}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);a=p.parse_args()
    print(json.dumps(package(a.output,a.cache)))
