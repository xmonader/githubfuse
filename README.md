# GithubFuse
Virtual github filesystem to mount your (and the others) repos directly.

## Why 
Github plays a major role in hosting packages and even some languages provide importing packages from github directly (Like golang).
Also, You can use custom import hooks to load your modules from github in python.

So I wanted to save us sometime and created GithubFuse filesystem to download the needed repos on demand of your application.


## How to run it?

### Config.ini
You should create `config.ini` file with proper access token
```
[githubapi]
token =  ACCESS TOKEN GOES HERE
```


```
python3 githubfuse.py --mountpoint="/mnt/githubtest" --githubdir="/tmp/githubtest"
```
It takes optional `--foreground` to show in foreground. (Turn it on and try to access files in your mountpoint and see it while cloning :) 



## How to use it from X language? 
```python
import importlib as imp
import sys

sys.path.append("/mnt/githubtest/xmonader/plyini")
import plyini

print(plyini)
```
## Notes
It depends of fusepy library.
Thanks to this article as well that got me started https://www.stavros.io/posts/python-fuse-filesystem/
