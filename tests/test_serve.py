import functools
import http.server
import threading
import urllib.request
import urllib.error
import pytest
from aftermath.serve import Handler

@pytest.fixture
def server(tmp_path):
    (tmp_path/'fixture.mp4').write_bytes(bytes(range(100)))
    instance=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(tmp_path)))
    thread=threading.Thread(target=instance.serve_forever,daemon=True);thread.start()
    yield 'http://127.0.0.1:'+str(instance.server_port)+'/fixture.mp4'
    instance.shutdown();instance.server_close();thread.join()

def test_full_media(server):
    with urllib.request.urlopen(server) as response:
        assert response.status==200
        assert response.read()==bytes(range(100))

def test_ranges(server):
    for value,expected,content_range in [('bytes=5-9',bytes(range(5,10)),'bytes 5-9/100'),('bytes=97-',bytes(range(97,100)),'bytes 97-99/100'),('bytes=-4',bytes(range(96,100)),'bytes 96-99/100'),('bytes=95-999',bytes(range(95,100)),'bytes 95-99/100')]:
        with urllib.request.urlopen(urllib.request.Request(server,headers={'Range':value})) as response:
            assert response.status==206
            assert response.headers['Content-Range']==content_range
            assert response.read()==expected

def test_invalid_ranges(server):
    for value in ['bytes=100-','bytes=9-3','bytes=-0','bytes=','bytes=0-1,4-5','items=1-2']:
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(urllib.request.Request(server,headers={'Range':value}))
        assert error.value.code==416
        assert error.value.headers['Content-Range']=='bytes */100'
