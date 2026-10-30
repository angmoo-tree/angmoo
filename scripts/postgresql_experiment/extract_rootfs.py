"""Materialize a digest-pinned flattened image without following host symlinks."""
import hashlib,json,os,pathlib,shutil,tarfile
from guard import require_owned_root,owned_path,RUN_ID

def extract(root:pathlib.Path,expected:str,*,archive_name='postgres-rootfs.tar.gz',destination_name='rootfs',record_name='rootfs.json'):
    root=require_owned_root(root)
    archive=owned_path(root,'artifacts/'+archive_name)
    destination=owned_path(root,destination_name)
    destination.mkdir(parents=True,exist_ok=True)
    if any(destination.iterdir()):raise ValueError('rootfs_not_empty')
    h=hashlib.sha256()
    with archive.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    if h.hexdigest()!=expected:raise ValueError('archive_digest_mismatch')
    directories=[];links=[];count=0
    def safe_path(name):
        p=pathlib.PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts:raise ValueError('archive_path_escape')
        target=destination.joinpath(*p.parts)
        if any(a.is_symlink() for a in target.parents if a!=destination.parent):
            raise ValueError('archive_symlink_parent')
        return target
    with tarfile.open(archive,'r:gz') as tf:
        for member in tf:
            target=safe_path(member.name)
            target.parent.mkdir(parents=True,exist_ok=True)
            if member.isdir():
                target.mkdir(exist_ok=True);directories.append((target,member.mode))
            elif member.issym():
                if target.exists() or target.is_symlink():raise ValueError('archive_duplicate_symlink')
                target.symlink_to(member.linkname)
            elif member.islnk():links.append((target,member.linkname,member.mode))
            elif member.isfile():
                if target.is_symlink():raise ValueError('archive_symlink_overwrite')
                with tf.extractfile(member) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
                target.chmod(member.mode&0o777)
            else:continue # Device nodes are supplied by the explicit /dev bind.
            count+=1
    # Android may forbid hardlinks. Copy verified regular image files instead;
    # never link image files to original app data or outside the image root.
    for target,link,mode in links:
        source=safe_path(link)
        if source.is_symlink() or not source.is_file():raise ValueError('archive_hardlink_target')
        if target.exists() or target.is_symlink():raise ValueError('archive_duplicate_hardlink')
        shutil.copyfile(source,target);target.chmod(mode&0o777)
    for path,mode in reversed(directories):path.chmod(mode&0o777)
    result={'run_id':RUN_ID,'archive_sha256':h.hexdigest(),'members':count,'hardlinks_copied':len(links),'rootfs':str(destination)}
    owned_path(root,'records/'+record_name).write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('root',type=pathlib.Path);p.add_argument('sha256');a=p.parse_args()
    print(json.dumps(extract(a.root,a.sha256)))
