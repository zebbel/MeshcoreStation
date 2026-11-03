"""Historical comparisons use saved evidence only, with explicit half-open windows."""
import json
import sqlite3
from contextlib import closing
from unittest.mock import Mock
import pytest
from test_statistics_visualization import station,A,B,C,D,NOW,add
from meshcorestation.storage import database,passive_stats,neighbor_snr
from meshcorestation.storage import repeater_comparison as journal
from meshcorestation.web import statistics_service as service


def change(at=NOW):
    with closing(sqlite3.connect(database.DB_FILE)) as db,db:
        return db.execute('INSERT INTO repeater_changes(public_key,recorded_at,description) VALUES(?,?,?)',(A,at,'Antenna change')).lastrowid


def snr(cfg,prefix,at,value,poll):
    assert neighbor_snr.record_page(database.DB_FILE,cfg,poll,at,at+1,[dict(pubkey=prefix,snr=value,secs_ago=0)])


def test_journal_server_time_edit_delete_and_membership(station,monkeypatch):
    monkeypatch.setattr(journal.time,'time',lambda:NOW)
    first=journal.mutate(database.DB_FILE,A,'create','New antenna')['change']
    assert first['recorded_at']==NOW and first['public_key']==A
    edited=journal.mutate(database.DB_FILE,A,'edit','New antenna, corrected',first['id'])['change']
    assert edited['recorded_at']==NOW and edited['description'].endswith('corrected')
    second=journal.mutate(database.DB_FILE,A,'create','Firmware update')['change']
    assert len(journal.journal(database.DB_FILE,A)['changes'])==2
    with pytest.raises(ValueError):journal.mutate(database.DB_FILE,B,'create','Not managed')
    with pytest.raises(ValueError):journal.mutate(database.DB_FILE,A,'delete',change_id=first['id'])
    add();path=passive_stats.statistics_path(database.DB_FILE,A);before=path.read_bytes()
    journal.mutate(database.DB_FILE,A,'delete',change_id=first['id'],confirm=True)
    assert path.read_bytes()==before and journal.journal(database.DB_FILE,A)['changes'][0]['id']==second['id']
    for value in ('','x'*501,'one\ntwo'):
        with pytest.raises(ValueError):journal.mutate(database.DB_FILE,A,'create',value)


def test_equal_windows_boundary_counts_rates_and_future(station):
    cid=change();add(at=NOW-100,payload=b'before');add(at=NOW,payload=b'boundary');add(at=NOW+100,payload=b'after');add(at=NOW+86400,payload=b'outside')
    passive_stats.record_coverage(database.DB_FILE,NOW-86400,NOW+86400)
    value=journal.aggregate(database.DB_FILE,A,cid,1,now=NOW+86400)
    assert value['before']['receptions']==1 and value['after']['receptions']==2
    assert value['before']['traffic_per_recorded_hour']==pytest.approx(1/24)
    assert value['after']['traffic_per_recorded_hour']==pytest.approx(2/24)
    assert value['before']['end']==value['after']['start']==NOW
    assert value['before']['complete'] and value['after']['complete']
    future=journal.aggregate(database.DB_FILE,A,cid,1,now=NOW)
    assert future['after']['future'] and not future['after']['complete']
    assert future['after']['receptions'] is None and future['after']['recorded_seconds']==0


def test_snr_matched_median_not_frequency_weighted_new_missing_and_dedup(station):
    cid=change();cfg=neighbor_snr.save_settings(database.DB_FILE,A,True,30)
    snr(cfg,'bb22',NOW-100,0,'b0')
    # Same source observation with aged report is not another independent sample.
    neighbor_snr.record_page(database.DB_FILE,cfg,'same',NOW-90,NOW-89,[dict(pubkey='bb22',snr=0,secs_ago=10)])
    for i in range(10):snr(cfg,'bb22',NOW+100+i*10,10,'a'+str(i))
    snr(cfg,'cc33',NOW-100,0,'c0');snr(cfg,'cc33',NOW+100,-2,'c1')
    snr(cfg,'dd44',NOW-100,4,'d0')
    station.add_new_repeater(type('Event',(),{'payload':dict(type=2,public_key='ee55'+'05'*30,adv_name='New')})(),observed=False)
    snr(cfg,'ee55',NOW+100,3,'e0')
    value=journal.aggregate(database.DB_FILE,A,cid,1,now=NOW+1000)
    assert value['median_snr_change']==4 # median(+10, -2), not a sample-weighted value
    paired={r['public_key']:r for r in value['matched']}
    assert paired[B]['before_samples']==1 and paired[B]['after_samples']==10
    assert paired[C]['difference_db']==-2
    assert value['newly_heard'][0]['name']=='New' and value['not_heard_after'][0]['public_key']==D
    assert value['after']['future'] and value['warnings']


def test_missing_history_and_overlapping_changes_preserve_unknowns(station):
    cid=change();change(NOW+100)
    value=journal.aggregate(database.DB_FILE,A,cid,7,now=NOW+200)
    assert value['median_snr_change'] is None and value['interpretation']=='Insufficient Data'
    assert value['before']['receptions'] is None and value['after']['traffic_per_recorded_hour'] is None
    assert value['overlapping_changes'] and not passive_stats.statistics_path(database.DB_FILE,A).exists()


def test_traffic_rate_excludes_observations_outside_recorded_intervals(station):
    cid=change();add(at=NOW-1800,payload=b'covered');add(at=NOW-7200,payload=b'unknown interval')
    passive_stats.record_coverage(database.DB_FILE,NOW-3600,NOW)
    result=journal.aggregate(database.DB_FILE,A,cid,1,now=NOW+1)
    assert result['before']['receptions']==2 and result['before']['covered_receptions']==1
    assert result['before']['traffic_per_recorded_hour']==1 and not result['before']['complete']


def test_api_protects_changes_and_rejects_client_timestamps(station):
    from flask import Flask
    from meshcorestation.web.comparison_api import register_comparison_routes
    app=Flask(__name__);register_comparison_routes(app);client=app.test_client();url='/api/repeater-comparison/changes'
    assert client.post(url,json={}).status_code==403
    headers={'X-Meshcore-Control':'1'}
    assert client.post(url,headers=headers,json=dict(public_key=A,action='create',description='x',timestamp=NOW)).status_code==400
    result=client.post(url,headers=headers,json=dict(public_key=A,action='create',description='Antenna'))
    assert result.status_code==200
    cid=result.json['change']['id'];stamp=result.json['change']['recorded_at']
    edited=client.post(url,headers=headers,json=dict(public_key=A,action='edit',id=cid,description='Updated')).json
    assert edited['change']['recorded_at']==stamp
    assert client.get(url+'?public_key='+A,headers=headers).json['changes'][0]['id']==cid


def test_comparison_worker_is_saved_only_and_preserves_rolling_views(station):
    cid=change();add(at=NOW-10)
    service.open_worker_service()
    try:
        result=service.comparison_view(database.DB_FILE,A,cid,1)
        assert result['ok'] and result['change']['id']==cid
        rolling=service.saved_view(database.DB_FILE,A,1)
        assert rolling['ok'] and 'hourly' in rolling and 'matched' not in rolling
    finally:service.close_worker();service.open_worker_service()


def test_collection_continues_without_changing_the_shared_comparison_snapshot(station,monkeypatch):
    from meshcorestation.storage import statistics_view
    cid=change();add(at=NOW-100,payload=b'before');add(at=NOW+100,payload=b'after')
    original=statistics_view.aggregate;sources=[]
    def calculate(*args,**kwargs):
        sources.append(kwargs['_source']);value=original(*args,**kwargs)
        if len(sources)==1:add(at=NOW+50,payload=b'arrived during calculation')
        return value
    monkeypatch.setattr(statistics_view,'aggregate',calculate)
    result=journal.aggregate(database.DB_FILE,A,cid,1,now=NOW+1000)
    assert sources[0] is sources[1] and sources[0] is not None
    assert result['before']['receptions']==result['after']['receptions']==1
    with sqlite3.connect(passive_stats.statistics_path(database.DB_FILE,A)) as db:
        assert db.execute('SELECT COUNT(*) FROM observations').fetchone()[0]==3
