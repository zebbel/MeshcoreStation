"""A deterministic, in-memory Companion protocol fixture. Never opens a radio."""
import copy
from types import SimpleNamespace as NS
from meshcore import EventType

KEY='ab'*32
OTHER='cd'*32
IDENTITY='11'*32


def event(kind,**payload):return NS(type=kind,payload=payload)


class Commands:
    def __init__(self,mc):
        self.mc=mc;self.ignore_writes=False;self.calls=[];self.remote={'name':'Hill repeater','flood.max':'8','lat':'49.6','lon':'8.6'};self.admin=False
    async def send(self,*args,**kwargs):return event(EventType.OK)
    async def get_time(self):
        import time
        return event(EventType.CURRENT_TIME,time=int(time.time()))
    async def set_time(self,stamp):return event(EventType.OK)
    async def send_appstart(self):return event(EventType.SELF_INFO,**self.mc.self_info)
    async def send_device_query(self):return event(EventType.DEVICE_INFO,max_channels=8,path_hash_mode=0,ver='fixture',model='Fixture Companion',fw_build='not live hardware')
    async def get_contacts(self,**kwargs):
        self.calls.append('get_contacts');return NS(type=EventType.CONTACTS,payload=copy.deepcopy(self.mc.contacts))
    async def add_contact(self,contact):
        self.calls.append('add_contact')
        if not self.ignore_writes:self.mc.contacts[contact['public_key']]=dict(contact)
        return event(EventType.OK)
    async def remove_contact(self,key):
        self.calls.append('remove_contact')
        if not self.ignore_writes:self.mc.contacts.pop(key,None)
        return event(EventType.OK)
    async def get_channel(self,index):
        self.calls.append('get_channel');name,secret=self.mc.channels[index]
        return event(EventType.CHANNEL_INFO,channel_idx=index,channel_name=name,channel_secret=secret)
    async def set_channel(self,index,name,secret):
        self.calls.append('set_channel')
        if not self.ignore_writes:self.mc.channels[index]=(name,secret)
        return event(EventType.OK)
    async def set_name(self,value):
        if not self.ignore_writes:self.mc.self_info['name']=value
        return event(EventType.OK)
    async def set_coords(self,lat,lon):
        if not self.ignore_writes:self.mc.self_info.update(adv_lat=lat,adv_lon=lon)
        return event(EventType.OK)
    async def set_tx_power(self,value):
        if not self.ignore_writes:self.mc.self_info['tx_power']=value
        return event(EventType.OK)
    async def set_radio(self,freq,bw,sf,cr):
        if not self.ignore_writes:self.mc.self_info.update(radio_freq=freq,radio_bw=bw,radio_sf=sf,radio_cr=cr)
        return event(EventType.OK)
    async def send_raw_packet(self,raw,priority=3):
        self.calls.append(('send_raw_packet',raw,priority));return event(EventType.OK)
    async def set_flood_scope(self,value):return event(EventType.OK)
    async def get_default_flood_scope(self):return event(EventType.DEFAULT_FLOOD_SCOPE)
    async def set_path_hash_mode(self,value):return event(EventType.OK)
    async def get_stats_core(self):return event(EventType.STATS_CORE,queue_len=0,battery_mv=4000,uptime_secs=600,errors=0)
    async def get_stats_radio(self):return event(EventType.STATS_RADIO,noise_floor=-120)
    async def get_stats_packets(self):return event(EventType.STATS_PACKETS,nb_recv=20,nb_sent=3)
    async def send_chan_msg(self,channel,message,timestamp=None):
        self.calls.append(('send_chan_msg',channel,message,timestamp));return event(EventType.OK)
    async def send_login_sync(self,contact,password,**kwargs):
        if password:self.admin=password=='admin'
        return event(EventType.LOGIN_SUCCESS,pubkey_prefix=contact['public_key'][:12],is_admin=self.admin,server_timestamp=2000000000,fw_ver_level=8)
    async def req_status_sync(self,contact,**kwargs):return {'pubkey_pre':contact['public_key'][:12],'bat':4000,'uptime':600,'tx_queue_len':0,'sent_flood':3,'recv_flood':20}
    async def req_telemetry_sync(self,contact,**kwargs):return [{'type':'voltage','channel':1,'value':4.0},{'type':'temperature','channel':1,'value':20.0}]
    async def req_neighbours_sync(self,contact,**kwargs):return {'neighbours':[{'pubkey':OTHER,'secs_ago':5,'snr':3}],'neighbours_count':1}
    async def req_acl_sync(self,contact,**kwargs):return []
    async def send_cmd(self,contact,command,timestamp=None):
        tag,text=command[:3],command[3:]
        if text.startswith('get '):reply='> '+self.remote.get(text[4:],'0')
        elif text.startswith('set '):
            _,field,value=text.split(' ',2)
            if not self.ignore_writes:self.remote[field]=value
            reply='OK'
        else:reply='OK'
        for callback in self.mc.subscriptions.get(EventType.CONTACT_MSG_RECV,[]):
            await callback(event(EventType.CONTACT_MSG_RECV,pubkey_prefix=contact['public_key'][:12],txt_type=0,text=tag+reply))
        return event(EventType.MSG_SENT)


class FakeMeshCore:
    def __init__(self):
        self.self_info=dict(public_key=IDENTITY,name='Fixture Companion',adv_lat=49.64,adv_lon=8.63,tx_power=10,max_tx_power=22,radio_freq=869.525,radio_bw=125.0,radio_sf=7,radio_cr=5)
        self.contacts={KEY:dict(public_key=KEY,adv_name='Hill repeater',type=2,adv_lat=49.6,adv_lon=8.6,flags=0,out_path='',out_path_len=-1,last_advert=123)}
        self.channels=[('Bot',bytes.fromhex('12'*16))]+[('',bytes(16)) for _ in range(7)]
        self.connection_manager=NS(is_connected=True);self.commands=Commands(self);self.subscriptions={}
    def subscribe(self,kind,callback):
        self.subscriptions.setdefault(kind,[]).append(callback)
        return NS(unsubscribe=lambda:self.subscriptions[kind].remove(callback))
    def unsubscribe(self, subscription):subscription.unsubscribe()
    def set_decrypt_channel_logs(self,*args):pass
    async def start_auto_message_fetching(self):pass
    async def disconnect(self):self.connection_manager.is_connected=False
