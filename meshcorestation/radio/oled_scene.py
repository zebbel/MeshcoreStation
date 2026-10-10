"""One renderer for dashboard previews and the real OLED. No radio requests."""
import math
from datetime import datetime
from meshcorestation.config import TIMEZONE
from meshcorestation.commands.context import percent
from meshcorestation.storage.voltage_store import config, latest


def render(db, page, now):
    # Imported lazily to keep the transport independent of storage/rendering.
    from meshcorestation.radio.oled import ascii_text
    cfg = config(db)
    newest = latest(db, cfg)
    sample = db.execute('''SELECT sampled_at,voltage FROM voltage_samples
        WHERE public_key=? AND voltage_channel=? AND sampled_at<=?
        AND voltage BETWEEN -1e308 AND 1e308
        ORDER BY sampled_at DESC,id DESC LIMIT 1''',
        (cfg['public_key'],cfg['voltage_channel'],now)).fetchone()
    age = max(0,now-sample['sampled_at']) if sample else None
    stale = bool(sample and ((newest and newest['voltage'] is None) or
                 age > max(120,cfg['interval_minutes']*120)))
    warnings = []
    if stale:
        warnings.append(f'Battery values marked * use the last successful reading ({int(age//60)} minutes old).'
                        + (' Latest read failed.' if newest and newest['voltage'] is None else ''))
    elif sample is None:
        warnings.append('No successful battery reading for the selected repeater and voltage channel.')
    node = db.execute('SELECT name FROM repeaters WHERE lower(public_key)=?', (cfg['public_key'],)).fetchone()
    voltage = sample['voltage'] if sample else None
    values = {'battery.name': node['name'] if node else 'Select battery node',
              'battery.voltage': voltage, 'battery.percent': percent(voltage) if voltage is not None else None,
              'battery.age_minutes': age/60 if age is not None else None,
              'battery.status': 'No reading' if sample is None else 'Old reading *' if stale else 'Current',
              'battery.sample_time': datetime.fromtimestamp(sample['sampled_at'], TIMEZONE).strftime('%H:%M') if sample else None,
              'repeaters.count': db.execute('SELECT count(*) FROM repeaters').fetchone()[0],
              'commands.count': db.execute('SELECT count(*) FROM logger').fetchone()[0]}
    for n,row in enumerate(db.execute('SELECT recv_time,sender,message,rssi,snr,path_len FROM logger ORDER BY recv_time DESC,id DESC LIMIT 3'),1):
        for field in ('sender','message','rssi','snr','path_len'):
            values[f'command{n}.{field}'] = row[field]
        values[f'command{n}.time'] = datetime.fromtimestamp(row['recv_time'], TIMEZONE).strftime('%H:%M') if row['recv_time'] else None
    texts, lines = [], []
    graphs = sum(e['kind']=='graph' for e in page['elements'])
    budget = 256 // max(1,graphs)
    for e in page['elements']:
        x,y,w,h = (e[k] for k in ('x','y','w','h'))
        if e['kind'] != 'graph':
            if e['kind']=='text':
                value = e['text']
            else:
                v = values.get(e['source'])
                v = '--' if v is None else (f"{v:.{e['precision']}f}" if isinstance(v,(int,float)) else str(v))
                if stale and e['source'] in ('battery.voltage','battery.percent'):
                    v = '*' + v
                value = e['label'] + v + e['units']
            texts.append((x,y,e['size'],ascii_text(value,min(21,w//(6*e['size'])))))
            continue
        start = now - e['hours']*3600
        columns = min(w-2,budget-2)
        if e['source'].startswith('battery.'):
            query = """SELECT id,sampled_at AS stamp,voltage AS value,interval_seconds AS gap FROM voltage_samples
                WHERE public_key=? AND voltage_channel=? AND sampled_at>=? AND sampled_at<=?"""
            params = (cfg['public_key'],cfg['voltage_channel'],start,now)
        else:
            field = {'commands.rssi':'rssi','commands.snr':'snr','commands.path_len':'path_len'}[e['source']]
            query = f'SELECT id,recv_time AS stamp,{field} AS value,0 AS gap FROM logger WHERE recv_time>=? AND recv_time<=?'
            params = (start,now)
        # Reduce in SQLite before transferring data into the radio event loop.
        # Keep the newest value in each pixel bucket, and preserve missing-data
        # and telemetry-gap markers even when a later sample shares that bucket.
        rows = db.execute(f"""WITH samples AS ({query}),
            gaps AS (SELECT *,lag(stamp) OVER (ORDER BY stamp,id) AS previous FROM samples),
            buckets AS (SELECT *,min(?,max(0,cast((stamp-?)/?*? AS INTEGER))) AS bucket,
                (value IS NULL OR (gap>0 AND stamp-previous>max(120,gap*2))) AS broken FROM gaps),
            ranked AS (SELECT *,row_number() OVER (PARTITION BY bucket ORDER BY stamp DESC,id DESC) AS rank,
                max(broken) OVER (PARTITION BY bucket) AS interrupted FROM buckets)
            SELECT stamp,value,gap,interrupted FROM ranked WHERE rank=1 ORDER BY stamp,id""",
            (*params,columns-1,start,float(now-start),columns-1))
        buckets = {}
        broken,previous = True,None
        for row in rows:
            v = row['value']
            broken = broken or bool(row['interrupted'])
            if v is None or not math.isfinite(v):
                broken,previous = True,None
                continue
            if e['source']=='battery.percent':
                v = percent(v)
                if v is None:
                    broken,previous = True,None
                    continue
            if previous is not None and row['gap'] and row['stamp']-previous>max(120,row['gap']*2):
                broken = True
            col = min(columns-1, max(0,int((row['stamp']-start)/(now-start)*(columns-1))))
            px = x+1+round(col/(max(1,columns-1))*(w-2))
            py = y+h-2-round((v-e['minimum'])/(e['maximum']-e['minimum'])*(h-2))
            py = min(y+h-2,max(y,py))
            old = buckets.get(col)
            buckets[col] = (px,py,broken or (old[2] if old else False))
            broken,previous = False,row['stamp']
        lines.extend([(x,y,x,y+h-1),(x,y+h-1,x+w-1,y+h-1)])
        previous = None
        for px,py,broken in buckets.values():
            lines.append((px,py,px,py) if previous is None or broken else (*previous,px,py))
            previous = px,py
    return {'texts':texts,'lines':lines,'warnings':warnings}
