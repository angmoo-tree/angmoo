"""Only owned synthetic key roots; never inspect or alter an installed key."""
import os
import sys
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.core.secret_file_access import create_secret_once, protect_existing_secret, inspect_windows_secret_access, SecretFileAccessError


def _ordinary_read_allowed(path):
    """Actual Windows AccessCheck with a token restricted to ordinary groups.

    Never impersonate the running process or create a Windows account.
    The token's restricted pass excludes the owner, SYSTEM and Administrators.
    """
    from app.core.secret_file_access import _WindowsAccess
    api=_WindowsAccess();c,w=api.c,api.w;p=c.c_void_p
    adv=api.advapi
    adv.ConvertStringSidToSidW.argtypes=[w.LPCWSTR,c.POINTER(p)];adv.ConvertStringSidToSidW.restype=w.BOOL
    adv.CreateRestrictedToken.argtypes=[w.HANDLE,w.DWORD,w.DWORD,p,w.DWORD,p,w.DWORD,p,c.POINTER(w.HANDLE)];adv.CreateRestrictedToken.restype=w.BOOL
    adv.DuplicateToken.argtypes=[w.HANDLE,c.c_int,c.POINTER(w.HANDLE)];adv.DuplicateToken.restype=w.BOOL
    adv.AccessCheck.argtypes=[p,w.HANDLE,w.DWORD,p,p,c.POINTER(w.DWORD),c.POINTER(w.DWORD),c.POINTER(w.BOOL)];adv.AccessCheck.restype=w.BOOL
    class SidAndAttributes(c.Structure):_fields_=[("sid",p),("attributes",w.DWORD)]
    token=w.HANDLE();restricted=w.HANDLE();impersonation=w.HANDLE();sids=[];security=p();handle=None
    try:
        api.checked(adv.OpenProcessToken(api.kernel.GetCurrentProcess(),0xB,c.byref(token)))
        for text in ("S-1-1-0","S-1-5-11","S-1-5-32-545"):
            sid=p();api.checked(adv.ConvertStringSidToSidW(text,c.byref(sid)));sids.append(sid)
        groups=(SidAndAttributes*len(sids))(*(SidAndAttributes(sid,0) for sid in sids))
        api.checked(adv.CreateRestrictedToken(token,1,0,None,0,None,len(groups),groups,c.byref(restricted)))
        api.checked(adv.DuplicateToken(restricted,2,c.byref(impersonation)))
        handle=api.open(path)
        assert adv.GetSecurityInfo(handle,1,7,None,None,None,None,c.byref(security))==0
        mapping=(w.DWORD*4)(0x120089,0x120116,0x1200A0,0x1F01FF)
        privileges=c.create_string_buffer(4096);length=w.DWORD(len(privileges));granted=w.DWORD();allowed=w.BOOL()
        api.checked(adv.AccessCheck(security,impersonation,1,mapping,privileges,c.byref(length),c.byref(granted),c.byref(allowed)))
        return bool(allowed.value)
    finally:
        if handle:api.kernel.CloseHandle(handle)
        if security:api.kernel.LocalFree(security)
        for sid in sids:api.kernel.LocalFree(sid)
        for owned in (impersonation,restricted,token):
            if owned:api.kernel.CloseHandle(owned)


@pytest.mark.skipif(os.name!="nt",reason="Windows native AccessCheck")
def test_ordinary_effective_read_is_removed_without_rotating_existing_key(tmp_path):
    from app.core.secret_file_access import _WindowsAccess
    path=tmp_path/"secrets/app-secret";create_secret_once(path,b"synthetic-unchanged-key")
    api=_WindowsAccess();c,w=api.c,api.w
    descriptor=c.c_void_p();handle=api.open(path,write_acl=True)
    try:
        text=f"D:P(A;;FA;;;{api.current_sid()})(A;;FA;;;SY)(A;;FA;;;BA)(A;;FR;;;AU)"
        api.checked(api.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(text,1,c.byref(descriptor),None))
        dacl=c.c_void_p();present=w.BOOL();defaulted=w.BOOL()
        api.checked(api.advapi.GetSecurityDescriptorDacl(descriptor,c.byref(present),c.byref(dacl),c.byref(defaulted)))
        assert api.advapi.SetSecurityInfo(handle,1,0x80000004,None,None,dacl,None)==0
    finally:
        api.kernel.CloseHandle(handle);api.kernel.LocalFree(descriptor)
    assert _ordinary_read_allowed(path)
    protect_existing_secret(path)
    assert not _ordinary_read_allowed(path)
    assert path.read_bytes()==b"synthetic-unchanged-key"


@pytest.mark.skipif(os.name!="nt",reason="Windows protected creation")
def test_temporary_file_is_protected_before_the_first_byte_is_written(tmp_path,monkeypatch):
    from app.core.secret_file_access import _WindowsAccess
    original=_WindowsAccess.open;observed=[]
    def open_file(self,path,**kwargs):
        handle=original(self,path,**kwargs)
        if kwargs.get("create"):
            observed.append(path)
            assert path.stat().st_size==0
            assert not _ordinary_read_allowed(path)
        return handle
    monkeypatch.setattr(_WindowsAccess,"open",open_file)
    create_secret_once(tmp_path/"secrets/app-secret",b"complete-key")
    assert len(observed)==1 and not observed[0].exists()


def test_unverified_access_preserves_existing_key(tmp_path,monkeypatch):
    path=tmp_path/"secrets/app-secret";create_secret_once(path,b"existing-key")
    if os.name=="nt":
        from app.core.secret_file_access import _WindowsAccess
        monkeypatch.setattr(_WindowsAccess,"inspect",lambda *args,**kwargs: (_ for _ in ()).throw(SecretFileAccessError()))
    else:
        os.chmod(path,0o644)
        monkeypatch.setattr(os,"fchmod",lambda *args: (_ for _ in ()).throw(SecretFileAccessError()))
    with pytest.raises(SecretFileAccessError):create_secret_once(path,b"replacement")
    assert path.read_bytes()==b"existing-key" and not list(path.parent.glob("*.tmp-*"))


@pytest.mark.skipif(os.name!="nt",reason="Windows directory replacement race")
def test_parent_cannot_be_replaced_during_protected_first_write(tmp_path,monkeypatch):
    from app.core.secret_file_access import _WindowsAccess
    original=_WindowsAccess.open;blocked=[]
    def open_file(self,path,**kwargs):
        handle=original(self,path,**kwargs)
        if kwargs.get("create"):
            with pytest.raises(OSError):path.parent.rename(tmp_path/"replacement")
            blocked.append(True)
        return handle
    monkeypatch.setattr(_WindowsAccess,"open",open_file)
    create_secret_once(tmp_path/"secrets/app-secret",b"race-protected-key")
    assert blocked==[True] and not (tmp_path/"replacement").exists()


def test_portable_io_contract_does_not_load_windows_apis(tmp_path,monkeypatch):
    import types
    import app.core.secret_file_access as module
    modes=[]
    # Exercise the portable branch with real IO and a permission-call port.
    # This proves import/IO separation, not Linux filesystem ACLs on Windows.
    portable=types.SimpleNamespace(**{name:getattr(os,name) for name in
        ("open","fdopen","fsync","link","fstat","close","fsencode","O_RDONLY","O_WRONLY","O_CREAT","O_EXCL")},
        name="posix",fchmod=lambda fd,mode:modes.append(mode))
    monkeypatch.setattr(module,"os",portable)
    monkeypatch.setattr(module,"_WindowsAccess",lambda:pytest.fail("Windows API must be lazy"))
    path=tmp_path/"portable/app-secret";module.create_secret_once(path,b"portable-key")
    module.create_secret_once(path,b"different-key")
    assert path.read_bytes()==b"portable-key"
    assert modes==([0o600,0o600] if os.name=="nt" else [])


def test_creation_restart_and_concurrent_winner_preserve_key_bytes(tmp_path):
    path=tmp_path/"secrets"/"app-secret"
    candidates=[b"synthetic-first-key",b"synthetic-other-key"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda content:create_secret_once(path,content),candidates))
    original=path.read_bytes()
    assert original in candidates
    create_secret_once(path,b"must-not-replace")
    protect_existing_secret(path)
    assert path.read_bytes()==original
    assert not list(path.parent.glob("*.tmp-*"))
    if os.name=="nt":
        report=inspect_windows_secret_access(path)
        assert not report.unsafe_access
        assert set(report.allowed_sids)<={report.current_sid,"S-1-5-18","S-1-5-32-544"}
        assert report.resolved_path.startswith("\\\\?\\")
    else:
        assert path.stat().st_mode&0o777==0o600


@pytest.mark.skipif(sys.platform != "linux", reason="Linux atomic publication")
def test_linux_secret_publication_never_uses_hardlinks(tmp_path, monkeypatch):
    import app.core.secret_file_access as module

    monkeypatch.setattr(module.os, "link", lambda *a, **k: pytest.fail("hardlink publication escapes PRoot data bind"))
    path = tmp_path / "secrets" / "app-secret"
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda value: create_secret_once(path, value), [b"first", b"second"]))
    original = path.read_bytes()
    assert original in (b"first", b"second")
    assert path.is_file() and not path.is_symlink()
    create_secret_once(path, b"must-not-replace")
    assert path.read_bytes() == original
    assert not list(path.parent.glob("*.tmp-*"))


def test_secret_publication_failure_keeps_destination_absent_and_cleans_temp(tmp_path, monkeypatch):
    import errno
    import app.core.secret_file_access as module

    def fail(*_args):
        raise OSError(errno.EIO, "injected publication failure")

    monkeypatch.setattr(module, "_publish_secret_no_replace", fail)
    path = tmp_path / "secrets" / "app-secret"
    with pytest.raises(SecretFileAccessError):
        create_secret_once(path, b"unpublished")
    assert not path.exists()
    assert not list(path.parent.glob("*.tmp-*"))


def test_link_path_preserves_target_and_does_not_generate_a_replacement(tmp_path):
    outside=tmp_path/"outside";outside.mkdir();source=outside/"app-secret";source.write_bytes(b"original")
    link=tmp_path/"linked"
    if os.name=="nt":
        import _winapi
        _winapi.CreateJunction(str(outside),str(link))
    else:link.symlink_to(outside,target_is_directory=True)
    try:
        with pytest.raises(SecretFileAccessError):create_secret_once(link/"app-secret",b"replacement")
        assert source.read_bytes()==b"original"
    finally:
        if os.name=="nt":link.rmdir()
        else:link.unlink()
