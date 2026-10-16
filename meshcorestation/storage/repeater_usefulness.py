"""Small, local-observation summary; never a network-wide health score."""
import sqlite3
from contextlib import closing


def summarize(db, key, since, days, now, health, main_path):
    span = days * 86400
    start = now - span
    where = 'target=? AND at>=? AND at<=? AND ambiguous=0'
    params = (key, start, now)
    unique = db.execute('SELECT COUNT(DISTINCT digest) FROM observations WHERE '+where, params).fetchone()[0]
    # Decode each distinct stored route once, not once per received RF copy.
    routes = db.execute("SELECT COUNT(DISTINCT (SELECT json_group_array(json_extract(value,'$.key')) FROM json_each(route))) FROM (SELECT DISTINCT route FROM observations WHERE "+where+")", params).fetchone()[0]
    active = {min(days*24-1,int(r[0])) for r in db.execute(
        'SELECT DISTINCT CAST((at-?)/3600 AS INTEGER) FROM observations WHERE '+where,(start,*params))}
    # Union both directions and exclude unknown/colliding identities.
    query = "SELECT json_extract(j.value,'$.key') AS key FROM (SELECT DISTINCT {column} AS hops FROM observations WHERE " + where + ") grouped,json_each(grouped.hops) j WHERE json_extract(j.value,'$.status')='matched' AND json_extract(j.value,'$.key')!=?"
    adjacent = db.execute('SELECT COUNT(*) FROM ('+query.format(column='previous')+' UNION '+query.format(column='following')+')',(*params,key,*params,key)).fetchone()[0]
    previous = None
    if since is not None and since <= now-2*span and days*2 <= 30 and not health.get('trimmed_at') and not health.get('dropped'):
        previous=db.execute('SELECT COUNT(DISTINCT digest) FROM observations WHERE target=? AND at>=? AND at<? AND ambiguous=0',(key,now-2*span,start)).fetchone()[0]
    trend = round((unique-previous)*100/previous,1) if previous else None
    replies = None
    try:
        with closing(sqlite3.connect(main_path.as_uri()+'?mode=ro',uri=True,timeout=2)) as main:
            # Only completed observation windows; no-reception is not failed delivery.
            total=main.execute("SELECT COUNT(*) FROM command_replies WHERE created_at>=? AND created_at<=? AND send_status IN ('accepted','uncertain')",(start,now-300)).fetchone()[0]
            forwarded=main.execute("SELECT COUNT(DISTINCT r.id) FROM command_replies r JOIN reply_observations o ON o.reply_id=r.id, json_each(o.route) j WHERE r.created_at>=? AND r.created_at<=? AND r.send_status IN ('accepted','uncertain') AND lower(json_extract(j.value,'$.public_key'))=?",(start,now-300,key)).fetchone()[0]
            replies=dict(forwarded=forwarded,total=total)
    except sqlite3.Error:
        pass
    return dict(unique=unique,active_hours=len(active),hours=days*24,routes=routes,neighbors=adjacent,
        trend=trend,previous_unique=previous,replies=replies,
        activity=[i in active for i in range(days*24)],
        partial=since is None or since>start or bool(health.get('trimmed_at') or health.get('dropped')),
        summary='Forwarding observed' if active else 'No forwarding observed')
