"""Resolve prefixes against the complete local knownRepeaters registry, no RF."""
import re


def with_neighbor_names(db,data):
    neighbors=[]
    for item in data.get('neighbours',[]):
        row=dict(item);prefix=str(row.get('pubkey','')).lower()
        for field in ('name','public_key','resolution'):row.pop(field,None)
        matches=[]
        if re.fullmatch('[0-9a-f]{2,64}',prefix) and len(prefix)%2==0:
            matches=db.execute('SELECT public_key,name FROM repeaters WHERE lower(public_key) LIKE ? LIMIT 2',(prefix+'%',)).fetchall()
        row.update(pubkey=prefix,resolution='matched' if len(matches)==1 else 'ambiguous' if matches else 'unknown')
        if len(matches)==1:row.update(public_key=matches[0][0],name=matches[0][1])
        else:row['name']=('Ambiguous repeater' if matches else 'Unknown Repeater')+' ('+prefix+'…)'
        neighbors.append(row)
    return {**data,'neighbours':neighbors}
