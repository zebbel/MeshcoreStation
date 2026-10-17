"""Read-only repeater optimization advisor; locally configurable review baselines."""
import json
import os
from pathlib import Path
from flask import request, Response
from meshcorestation.config import DATA_DIR
from meshcorestation.storage import passive_stats
from meshcorestation.web.http import control_request_error, json_response

FILE = DATA_DIR / 'repeater-advisor.json'
FIELDS = {
    'flood.max': (0,64,16),
    'flood.max.unscoped': (0,64,3),
    'flood.max.advert': (0,64,6),
    'advert.interval': (0,240,240),
    'flood.advert.interval': (0,168,48),
}
LOOPS = ('off','minimal','moderate','strict')
DEFAULT = {'targets': {k: bounds[2] for k,bounds in FIELDS.items()} | {'loop.detect':'minimal'},
           'min_copies': 100, 'min_days': 7, 'enabled': {k:True for k in (*FIELDS,'loop.detect')}}
NOTES = {
 'flood.max': 'Overall flood ceiling; long rural routes may need more hops.',
 'flood.max.unscoped': 'Unscoped forwarding ceiling; lowering it can disconnect unscoped users.',
 'flood.max.advert': 'Flood advertisement ceiling; also subject to other applicable limits.',
 'advert.interval': 'Zero-hop local advertisement interval in minutes (not forwarded).',
 'flood.advert.interval': 'Flood advertisement interval in hours (0 disables).',
 'loop.detect': 'Loop suppression policy; repeated payloads alone do not prove loops.',
}

def config():
    try:
        saved=json.loads(FILE.read_text(encoding='utf-8'))
        return validate(saved)
    except (OSError,ValueError,TypeError,KeyError):
        return json.loads(json.dumps(DEFAULT))

def validate(data):
    if not isinstance(data,dict) or set(data)!={'targets','min_copies','min_days','enabled'}:
        raise ValueError('Invalid advisor configuration.')
    if not isinstance(data['targets'],dict) or set(data['targets'])!=set(DEFAULT['targets']):
        raise ValueError('Invalid target fields.')
    if not isinstance(data['enabled'],dict) or set(data['enabled'])!=set(DEFAULT['enabled']) or any(type(v) is not bool for v in data['enabled'].values()):
        raise ValueError('Invalid enabled fields.')
    for field,(low,high,_) in FIELDS.items():
        value=data['targets'][field]
        if type(value) is not int or not low<=value<=high:
            raise ValueError('Invalid value for '+field)
    if data['targets']['loop.detect'] not in LOOPS:
        raise ValueError('Invalid loop detection mode.')
    if type(data['min_copies']) is not int or not 0<=data['min_copies']<=100000:
        raise ValueError('Invalid minimum copies.')
    if data['min_days'] not in (1,7,30) or type(data['min_days']) is not int:
        raise ValueError('Invalid observation period.')
    return data

def recommendations(current, settings, snapshot):
    # Missing config is never interpreted as zero; passive counts are local evidence only.
    copies=snapshot.get('copies',0)
    healthy=copies>=settings['min_copies'] and not snapshot.get('health',{}).get('error')
    output=[]
    for field,target in settings['targets'].items():
        if not settings['enabled'][field]:
            continue
        value=current.get(field)
        if value is None or value=='':
            status='Not evaluated'; explanation='Current repeater value not provided.'
        elif str(value)==str(target):
            status='Matches reference'; explanation='Current value matches the editable reference.'
        else:
            status='Review only'; explanation='Different from the editable community reference; do not apply without checking network topology and scope use.'
        output.append({'field':field,'current':value,'reference':target,'status':status,
                       'note':NOTES[field], 'explanation':explanation,
                       'confidence':'limited' if healthy else 'insufficient observations'})
    return output

def register_advisor_routes(server):
    @server.route('/repeater-advisor')
    def advisor_page():
        html=Path(__file__).with_name('repeater_advisor.html').read_text(encoding='utf-8')
        return Response(html,mimetype='text/html',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

    @server.route('/api/repeater-advisor',methods=['GET','POST'])
    def advisor_api():
        if control_request_error():
            return json_response({'ok':False,'error':'Open advisor from this dashboard.'},403)
        if request.method=='POST':
            body=request.get_json(silent=True)
            try:
                if not isinstance(body,dict): raise ValueError('Expected JSON object.')
                data=validate(body)
                FILE.parent.mkdir(parents=True,exist_ok=True)
                temp=FILE.with_suffix('.tmp')
                with open(temp,'w',encoding='utf-8') as stream:
                    json.dump(data,stream,indent=2)
                os.replace(temp,FILE)
            except (ValueError,TypeError,OSError) as exc:
                return json_response({'ok':False,'error':str(exc)},400)
        settings=config()
        try:
            snapshot=passive_stats.snapshot(settings['min_days'])
            # Snapshot is for the selected repeater only; never aggregate other repeaters.
            summary={'copies':snapshot.get('copies',0),'unique':snapshot.get('unique',0),
                     'scoped':snapshot.get('scoped'),'types':snapshot.get('types'),
                     'health':snapshot.get('health'),'days':settings['min_days']}
        except Exception:
            summary={'copies':0,'unique':0,'health':{'error':'Statistics unavailable'},'days':settings['min_days']}
        return json_response({'ok':True,'settings':settings,'statistics':summary,'notes':NOTES})
