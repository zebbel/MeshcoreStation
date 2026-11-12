"""One saved-data calculation in a fresh interpreter; never imports radio/runtime."""
import json
import logging
import sqlite3
import resource
import time
import sys
from pathlib import Path
from meshcorestation.storage.statistics_view import aggregate,QueryTimeout

MAX_RESULT_BYTES=8*1024*1024


def main():
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    cpu_started=time.process_time()
    try:
        path,key,days=sys.argv[1:4]
        if len(sys.argv)>4:
            from meshcorestation.storage.repeater_comparison import aggregate as comparison
            value=comparison(Path(path),key,int(sys.argv[4]),int(days))
        else:value=aggregate(Path(path),key,int(days))
    except QueryTimeout as exc:value=dict(ok=False,error_code='QUERY_TIMEOUT',stage=exc.stage,diagnostics=exc.diagnostics)
    except sqlite3.Error as exc:value=dict(ok=False,error_code='SQLITE_ERROR',sqlite_code=getattr(exc,'sqlite_errorcode',None))
    except OSError:value=dict(ok=False,error_code='STORAGE_ERROR')
    except ValueError:value=dict(ok=False,error_code='INVALID_SELECTION')
    except Exception:value=dict(ok=False,error_code='WORKER_ERROR')
    if value.get('ok'):
        value.setdefault('diagnostics',{}).update(worker_cpu_ms=round((time.process_time()-cpu_started)*1000,3),worker_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    encoded=json.dumps(value,allow_nan=False).encode('utf-8')
    if len(encoded)>MAX_RESULT_BYTES:encoded=b'{"ok":false,"error_code":"RESULT_TOO_LARGE"}'
    sys.stdout.buffer.write(encoded)


if __name__=='__main__':main()
