import os
import tempfile
os.environ['DATABASE_URL']='sqlite:///'+tempfile.mktemp(suffix='.db')
os.environ['KEY_FILE']=tempfile.mktemp(suffix='.key')

# Unit tests must not depend on host proxy configuration.
for key in ('ALL_PROXY','all_proxy','HTTPS_PROXY','https_proxy','HTTP_PROXY','http_proxy'):
    os.environ.pop(key,None)
