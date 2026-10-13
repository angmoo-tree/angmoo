"""Narrow managed-secret access, atomic publication, and privacy-safe inspection.

Windows APIs are loaded only on Windows. Inspection never reads secret bytes.
Existing keys are never rotated or replaced when access cannot be verified.
"""
import os
import secrets
import stat
from pathlib import Path
from dataclasses import dataclass
from contextlib import contextmanager


class SecretFileAccessError(RuntimeError):
    def __init__(self):
        super().__init__("app_secret_access_unverified")


@dataclass(frozen=True)
class SecretAccess:
    resolved_path: str
    owner_sid: str
    current_sid: str
    allowed_sids: tuple[str, ...]
    unsafe_access: bool


class _WindowsAccess:
    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w
        self.c,self.w=c,w
        self.kernel=c.WinDLL("kernel32",use_last_error=True)
        self.advapi=c.WinDLL("advapi32",use_last_error=True)
        p=c.c_void_p
        signatures={
            "GetCurrentProcess":([],w.HANDLE),"CloseHandle":([w.HANDLE],w.BOOL),
            "LocalFree":([p],p),
            "CreateFileW":([w.LPCWSTR,w.DWORD,w.DWORD,p,w.DWORD,w.DWORD,w.HANDLE],w.HANDLE),
            "CreateDirectoryW":([w.LPCWSTR,p],w.BOOL),
            "GetFinalPathNameByHandleW":([w.HANDLE,w.LPWSTR,w.DWORD,w.DWORD],w.DWORD),
            "GetFileInformationByHandleEx":([w.HANDLE,c.c_int,p,w.DWORD],w.BOOL),
        }
        for name,(args,result) in signatures.items():
            function=getattr(self.kernel,name);function.argtypes=args;function.restype=result
        signatures={
            "OpenProcessToken":([w.HANDLE,w.DWORD,c.POINTER(w.HANDLE)],w.BOOL),
            "GetTokenInformation":([w.HANDLE,c.c_int,p,w.DWORD,c.POINTER(w.DWORD)],w.BOOL),
            "ConvertSidToStringSidW":([p,c.POINTER(p)],w.BOOL),
            "ConvertStringSecurityDescriptorToSecurityDescriptorW":([w.LPCWSTR,w.DWORD,c.POINTER(p),p],w.BOOL),
            "GetSecurityDescriptorDacl":([p,c.POINTER(w.BOOL),c.POINTER(p),c.POINTER(w.BOOL)],w.BOOL),
            "GetSecurityInfo":([w.HANDLE,c.c_int,w.DWORD,c.POINTER(p),p,c.POINTER(p),p,c.POINTER(p)],w.DWORD),
            "SetSecurityInfo":([w.HANDLE,c.c_int,w.DWORD,p,p,p,p],w.DWORD),
            "GetAce":([p,w.DWORD,c.POINTER(p)],w.BOOL),
        }
        for name,(args,result) in signatures.items():
            function=getattr(self.advapi,name);function.argtypes=args;function.restype=result
        class Attributes(c.Structure):
            _fields_=[("length",w.DWORD),("descriptor",p),("inherit",w.BOOL)]
        self.Attributes=Attributes

    def checked(self,value):
        if not value:raise SecretFileAccessError()
        return value

    def sid(self,pointer):
        c=self.c;result=c.c_void_p()
        self.checked(self.advapi.ConvertSidToStringSidW(pointer,c.byref(result)))
        try:return c.wstring_at(result)
        finally:self.kernel.LocalFree(result)

    def current_sid(self):
        c,w=self.c,self.w;token=w.HANDLE()
        self.checked(self.advapi.OpenProcessToken(self.kernel.GetCurrentProcess(),8,c.byref(token)))
        try:
            length=w.DWORD()
            self.advapi.GetTokenInformation(token,1,None,0,c.byref(length))
            data=c.create_string_buffer(length.value)
            self.checked(self.advapi.GetTokenInformation(token,1,data,length,c.byref(length)))
            return self.sid(c.cast(data,c.POINTER(c.c_void_p))[0])
        finally:self.kernel.CloseHandle(token)

    def descriptor(self,directory=False):
        c=self.c;descriptor=c.c_void_p()
        flags="OICI" if directory else ""
        sid=self.current_sid()
        text=f"D:P(A;{flags};FA;;;{sid})(A;{flags};FA;;;SY)(A;{flags};FA;;;BA)"
        self.checked(self.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(text,1,c.byref(descriptor),None))
        return descriptor

    def open(self,path,*,write_acl=False,create=False,descriptor=None,share=7,attributes_only=False,read_data=False):
        c=self.c
        attributes=self.Attributes(c.sizeof(self.Attributes),descriptor,False) if descriptor else None
        access=0xC0000000 if create else 0x00020000|0x80|(0x00040000 if write_acl else 0)
        if read_data:access|=1
        if attributes_only:access=0x80
        handle=self.kernel.CreateFileW(str(path),access,share,c.byref(attributes) if attributes else None,
            1 if create else 3,0x02200000 if not create else 0x00200000,None)
        if handle==c.c_void_p(-1).value:
            if create and c.get_last_error() in (80,183):raise FileExistsError()
            raise SecretFileAccessError()
        return handle

    def inspect(self,path,*,repair=False):
        c,w=self.c,self.w;handle=self.open(path,write_acl=repair)
        security=c.c_void_p()
        try:
            attributes=(w.DWORD*2)()
            self.checked(self.kernel.GetFileInformationByHandleEx(handle,9,attributes,c.sizeof(attributes)))
            if attributes[0]&0x400:raise SecretFileAccessError() # Reparse point.
            directory=bool(attributes[0]&0x10)
            final=c.create_unicode_buffer(32768)
            length=self.kernel.GetFinalPathNameByHandleW(handle,final,len(final),0)
            if not length or length>=len(final):raise SecretFileAccessError()
            owner=c.c_void_p();dacl=c.c_void_p()
            if self.advapi.GetSecurityInfo(handle,1,5,c.byref(owner),None,c.byref(dacl),None,c.byref(security)):
                raise SecretFileAccessError()
            owner_sid=self.sid(owner);current=self.current_sid()
            if owner_sid not in (current,"S-1-5-18","S-1-5-32-544"):raise SecretFileAccessError()
            allowed=[];unsafe=not bool(dacl);has_deny=False
            if dacl:
                # ACL header: byte revision, byte padding, ushort size/count/padding.
                count=c.cast(dacl,c.POINTER(c.c_ushort))[2]
                for index in range(count):
                    ace=c.c_void_p();self.checked(self.advapi.GetAce(dacl,index,c.byref(ace)))
                    kind,flags=c.string_at(ace,2)
                    if flags&8:continue # Inherit-only does not grant this object's access.
                    if kind not in (0,1):raise SecretFileAccessError()
                    if kind==1:
                        has_deny=True
                        continue
                    sid=self.sid(ace.value+8);allowed.append(sid)
                    mask=c.cast(ace.value+4,c.POINTER(w.DWORD))[0]
                    sensitive=0x500D0046 if directory else 0xD00D0003
                    if sid not in (current,"S-1-5-18","S-1-5-32-544") and mask&sensitive:unsafe=True
            # Do not rewrite a complex ACL whose effective grant we cannot prove.
            # Deny/group membership semantics need an actual access token, not an
            # inference from an allow SID. Leave the original ACL and key intact.
            if unsafe and has_deny:raise SecretFileAccessError()
            if unsafe and repair:
                descriptor=self.descriptor(directory);present=w.BOOL();replacement=c.c_void_p();defaulted=w.BOOL()
                try:
                    self.checked(self.advapi.GetSecurityDescriptorDacl(descriptor,c.byref(present),c.byref(replacement),c.byref(defaulted)))
                    if self.advapi.SetSecurityInfo(handle,1,0x80000004,None,None,replacement,None):raise SecretFileAccessError()
                finally:self.kernel.LocalFree(descriptor)
                return self.inspect(path)
            if not directory:
                # Prove that the actual current token can open the key for read,
                # without reading a byte or changing its owner/permissions.
                readable=self.open(path,read_data=True)
                self.kernel.CloseHandle(readable)
            return SecretAccess(final.value,owner_sid,current,tuple(allowed),unsafe)
        finally:
            if security:self.kernel.LocalFree(security)
            self.kernel.CloseHandle(handle)


def inspect_windows_secret_access(path:Path)->SecretAccess:
    if os.name!="nt":raise SecretFileAccessError()
    return _WindowsAccess().inspect(path)


def _no_links(path):
    for node in (path,*path.parents):
        if node.is_symlink() or node.is_junction():raise SecretFileAccessError()


@contextmanager
def _physical_parents(path):
    """Hold every Windows directory against rename/reparse replacement during IO."""
    handles=[]
    api=_WindowsAccess() if os.name=="nt" else None
    try:
        if api:
            for parent in reversed(path.parents):
                handle=api.open(parent,share=3,attributes_only=True)
                handles.append(handle)
                attributes=(api.w.DWORD*2)()
                api.checked(api.kernel.GetFileInformationByHandleEx(handle,9,attributes,api.c.sizeof(attributes)))
                if not attributes[0]&0x10 or attributes[0]&0x400:raise SecretFileAccessError()
        yield
    finally:
        if api:
            for handle in reversed(handles):api.kernel.CloseHandle(handle)


def protect_existing_secret(path:Path,*,protect_parent=False)->None:
    path=Path(path);_no_links(path)
    with _physical_parents(path):
        _protect_existing_secret(path,protect_parent=protect_parent)


def _protect_existing_secret(path,*,protect_parent=False):
    if os.name=="nt":
        api=_WindowsAccess()
        for managed in (path.parent,path) if protect_parent else (path,):
            if api.inspect(managed).unsafe_access and api.inspect(managed,repair=True).unsafe_access:
                raise SecretFileAccessError()
    else:
        descriptor=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
        try:
            mode=os.fstat(descriptor).st_mode
            if not stat.S_ISREG(mode):raise SecretFileAccessError()
            if mode&0o077:os.fchmod(descriptor,0o600)
        finally:os.close(descriptor)


def create_secret_once(path:Path,content:bytes)->None:
    """Publish complete protected bytes exactly once, preserving a racing winner."""
    path=Path(path);_no_links(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with _physical_parents(path):
        _create_secret_once(path,content)


def _create_secret_once(path,content):
    try:path.lstat()
    except FileNotFoundError:pass
    except OSError as exc:raise SecretFileAccessError() from exc
    else:
        protect_existing_secret(path)
        return
    if os.name=="nt":
        api=_WindowsAccess()
        if api.inspect(path.parent).unsafe_access:api.inspect(path.parent,repair=True)
    temporary=path.with_name(path.name+".tmp-"+secrets.token_hex(12))
    descriptor=None;handle=None
    try:
        if os.name=="nt":
            import msvcrt
            descriptor=api.descriptor()
            handle=api.open(temporary,create=True,descriptor=descriptor)
            fd=msvcrt.open_osfhandle(handle,os.O_RDWR|os.O_BINARY);handle=None
        else:
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
        with os.fdopen(fd,"wb") as stream:
            stream.write(content);stream.flush();os.fsync(stream.fileno())
        try:os.link(temporary,path)
        except FileExistsError:pass # Never replace the first key.
        protect_existing_secret(path)
    except OSError as exc:
        raise SecretFileAccessError() from exc
    finally:
        if os.name=="nt":
            if handle is not None:api.kernel.CloseHandle(handle)
            if descriptor is not None:api.kernel.LocalFree(descriptor)
        temporary.unlink(missing_ok=True)
