"""
GithubFS is a solution to mount github.com in your filesystem.
"""
import os
import argparse
import re
from configparser import ConfigParser
from functools import lru_cache
import stat
import fuse
import github


def logged(meth):
    """
    General decorator for instance methods.

    @param meth MethodType: instance method. 
    """
    def wrapper(*args):
        print("LOGGING {meth} {args}".format(**locals()))
        return meth(*args) #self, ... other args
    return wrapper

def get_token(filename='config.ini'):
    """
    Get api token from ini filename
    @param filename str: filename
    """
    cp = ConfigParser()
    cp.read(filename)
    token = cp.get('githubapi', 'token')
    return token


def githubclient(token):
    """
    Get github client using an api token.
    @param token str
    """
    return github.Github(token)

ghclient = githubclient(get_token("config.ini"))


@lru_cache(maxsize=128)
def get_repos_user(user='xmonader'):
    """List repos of a user
    @param user str: username
    """
    u = ghclient.get_user(login=user)
    repos = u.get_repos()
    repos_list = []
    for i in range(20):
        page = repos.get_page(i)
        if len(page) == 0:
            break
        repos_list.extend(repos.get_page(i))
    return repos_list


def get_repo_user(fulllink):

    return ghclient.get_repo(fulllink)


class FakeStat():
    """Fake stat for remote files."""
    st_atime = 0
    st_ctime = 0
    st_gid = 0
    st_mode = 0o755
    st_mtime = 0
    st_nlink = 0
    st_size = 0
    st_uid = 0

    def set_isdir(self):
        """
        Set S_IFDIR flag on st_mode
        Should be used with the main user profile page and root repository directory
        """
        self.st_mode |= stat.S_IFDIR


class GithubOperations(fuse.Operations, fuse.LoggingMixIn):
    """
    Where all github fs magic happens.

    We define the operations of the fuse filesystem (open, readdir, unlink ... etc)
    """
    def __init__(self, root='/tmp/github'):
        self.root = root
        self.verbose = True
        if not os.path.exists(self.root):
            os.mkdir(self.root)

    def _full_path(self, path):
        path = re.sub("@\w+", "", path)  # remove commit-ish
        if not isinstance(path, str):
            path = path.decode()
        path = path.lstrip("/")
        fullpath = os.path.join(self.root, path)
        return fullpath

    @logged
    def chmod(self, path, mode):
        full_path = self._full_path(path)
        return os.chmod(full_path, mode)
    @logged
    def chown(self, path, uid, gid):
        full_path = self._full_path(path)
        return os.chown(full_path, uid, gid)

    @logged
    def getattr(self, path, fh=None):
        full_path = self._full_path(path)

        if os.path.exists(full_path):
            st = os.stat(full_path)
            return dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime',
                                                            'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid'))
        else:
            fakestat = FakeStat()
            # user profile, repos are directories.
            if path.count("/") >= 0:  # userprofile or repo
                fakestat.set_isdir()

            return {x: y for x, y in fakestat.__dict__.items() if 'st' in x}
    @logged
    def readdir(self, path, fh):
        #/xmonader
        #/xmonader/plyini
        #/xmonader/plyini@master/
        dirents = ['.', '..']
        full_path = self._full_path(path)
        path = path.lstrip("/")  # /xmonader/plyini[@COMMITISH]

        branchname = "master"
        ms = re.findall("@(\w+)", path) 
        if ms:
            branchname = ms[0]

        if path == '': # root directory of github:
            dirents.extend(os.listdir(full_path))
        else:
            if path.count("/") == 0:
                repos = get_repos_user(path.strip("/"))
                reposdirs = [x.full_name.split("/")[1] for x in repos]
                dirents.extend(reposdirs)

            if not os.path.exists(full_path) and path.count("/") == 1:
                # DO SHALLOW CLONE. 
                repopath = path
                if "@" in path:
                    repopath = re.findall("(.+)@", path)[0]
                
                os.system("git clone https://github.com/{repopath} {full_path} -b {branchname}".format(**locals())) 

            if os.path.exists(full_path):
                dirents.extend(os.listdir(full_path))

        # unique entries (because we might have them already in the
        # filesystem.
        dirents = set(dirents)
        for r in dirents:
            yield r
    @logged
    def readlink(self, path):
        pathname = os.readlink(self._full_path(path))
        if pathname.startswith("/"):
            # Path name is absolute, sanitize it.
            return os.path.relpath(pathname, self.root)
        else:
            return pathname

    @logged
    def mknod(self, path, mode, dev):
        return os.mknod(self._full_path(path), mode, dev)

    @logged
    def rmdir(self, path):
        full_path = self._full_path(path)
        return os.rmdir(full_path)

    @logged
    def mkdir(self, path, mode):
        return os.mkdir(self._full_path(path), mode)

    @logged
    def statfs(self, path):
        full_path = self._full_path(path)
        stv = os.statvfs(full_path)
        return dict((key, getattr(stv, key)) for key in ('f_bavail', 'f_bfree',
                                                         'f_blocks', 'f_bsize', 'f_favail', 'f_ffree', 'f_files', 'f_flag',
                                                         'f_frsize', 'f_namemax'))
    @logged
    def unlink(self, path):
        return os.unlink(self._full_path(path))

    @logged
    def symlink(self, name, target):
        return os.symlink(name, self._full_path(target))

    @logged
    def rename(self, old, new):
        return os.rename(self._full_path(old), self._full_path(new))

    @logged
    def link(self, target, name):
        return os.link(self._full_path(target), self._full_path(name))

    @logged
    def utimens(self, path, times=None):
        return os.utime(self._full_path(path), times)

    @logged
    def open(self, path, flags):
        full_path = self._full_path(path)
        return os.open(full_path, flags)

    @logged
    def create(self, path, mode, fi=None):
        full_path = self._full_path(path)
        return os.open(full_path, os.O_WRONLY | os.O_CREAT, mode)

    @logged
    def read(self, path, length, offset, fh):
        os.lseek(fh, offset, os.SEEK_SET)
        return os.read(fh, length)

    @logged
    def write(self, path, buf, offset, fh):
        os.lseek(fh, offset, os.SEEK_SET)
        return os.write(fh, buf)

    @logged
    def truncate(self, path, length, fh=None):
        full_path = self._full_path(path)
        with open(full_path, 'r+') as f:
            f.truncate(length)

    @logged
    def flush(self, path, fh):
        return os.fsync(fh)

    @logged
    def release(self, path, fh):
        return os.close(fh)

    @logged
    def fsync(self, path, fdatasync, fh):
        return self.flush(path, fh)


def mount(githubdir, mntpoint, verbose=True, foreground=True):
    """
    Mount GithubFuse filesystem to a mountpoint

    @param githubdir str: directory where we keep our github packages [cached]
    @param mntpoint  str: mount point to mount the fuse filesystem to. (i.e /mnt/github.com)
    """
    fuse.FUSE(GithubOperations(root=githubdir),
              mntpoint, nothreads=True, foreground=foreground)

def cli():
    """Entry point for githubfuse"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--mountpoint", dest="mountpoint", help="Mount point")
    parser.add_argument("--githubdir", dest="githubdir", help="Github caching directory.")
    parser.add_argument("--foreground", dest="foreground", action="store_true", help="Show in foreground.")

    args = parser.parse_args()
    mount(args.githubdir, mntpoint=args.mountpoint, foreground=args.foreground)

if __name__ == "__main__":
    cli()
