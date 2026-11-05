"""Own the radio session, battery worker, and graceful reconnects in one process."""
import asyncio
import time
from meshcorestation.bridge import bridge
from meshcorestation.radio.companion import Companion
from meshcorestation.radio.companion_control import CompanionControl
from meshcorestation.radio.voltage_monitor import VoltageMonitor

class Runtime:

    def __init__(self, logger, database):
        self.logger, self.database = (logger, database)
        self.companion = self.control = self.voltage = None
        self.reconnect_requested = asyncio.Event()
        self.requests = set()
        self.rooms = None
        self.room_error = ''
        self.close_error = None
        self.device_info = {}
        from pathlib import Path
        from meshcorestation.radio.statistics_collector import Collector
        main_path = Path(database.db.execute("PRAGMA database_list").fetchone()[2])
        self.room_path = main_path.parent / 'rooms.db'
        self.statistics = Collector(main_path, logger)
        from meshcorestation.radio.neighbor_monitor import NeighborMonitor
        self.neighbor_monitor = NeighborMonitor(self, main_path)

    async def dispatch(self, payload):
        """Serialize control changes with bot replies and telemetry requests."""
        if payload.get('operation') == 'room_bot':
            from meshcorestation.rooms.service import RoomService
            service = RoomService(self.room_path)
            room = payload.get('room')
            if type(room) is not int or room < 1:
                return {'ok': False, 'error': 'Select a room.'}
            companion = self.companion
            if companion is None:
                service.set_bot(room)
                return {'ok': True}
            async with companion.control_lock:
                if companion is not self.companion:
                    return {'ok': False, 'error': 'Companion reconnected; retry selection.'}
                service.set_bot(room)
                companion.reply_retries.cancel('Bot destination changed; pending retries cancelled.')
                companion.room_bot_id = room
                selected = service.config(room)
                companion.room_bot_name = selected['name']
                companion.room_bot_public_key = selected['public_key']
            return {'ok': True}
        control, companion = (self.control, self.companion)
        if control is None or companion is None:
            return {'ok': False, 'error': 'Companion offline. Select a serial port and check its connection.'}
        task = asyncio.current_task()
        self.requests.add(task)
        try:
            async with companion.control_lock:
                if control is not self.control:
                    return {'ok': False, 'error': 'Companion reconnected; refresh before retrying.'}
                if payload.get('operation') == 'room_restart':
                    started = await self.start_rooms()
                    return {'ok': started, 'error': self.room_error}
                if payload.get('operation') in {'name', 'position', 'tx_power', 'radio', 'path_hash_size', 'default_scope', 'add_channel', 'delete_channel', 'set_bot_channel'}:
                    companion.reply_retries.cancel('Companion configuration change requested; pending retries cancelled.')
                result = await control.execute(payload)
                if payload.get('operation') == 'set_bot_channel' and result.get('ok'):
                    from meshcorestation.rooms.service import RoomService
                    RoomService(self.room_path).clear_bot()
                    companion.room_bot_id = companion.room_bot_name = companion.room_bot_public_key = None
                return result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return {'ok': False, 'error': str(exc), 'note': 'Read settings again before retrying a change.'}
        finally:
            self.requests.discard(task)

    async def close_session(self):
        self.control = None
        if self.neighbor_monitor.task:
            await self.neighbor_monitor.close()
        if self.companion is not None:
            await self.companion.reply_retries.close()
        for task in tuple(self.requests):
            task.cancel()
        await asyncio.gather(*tuple(self.requests), return_exceptions=True)
        if self.rooms is not None:
            await self.rooms.close()
            self.rooms = None
            if self.companion is not None:
                self.companion.room_worker = None
        if self.voltage is not None:
            await self.voltage.close()
            self.voltage = None
        if self.companion is not None:
            try:
                await asyncio.wait_for(self.companion.disconnect(), timeout=10)
            except Exception as exc:
                self.close_error = exc
                self.logger.warning('Closing companion: %s', exc)
            self.companion = None

    async def start_rooms(self):
        if self.rooms:
            await self.rooms.close()
        try:
            from meshcorestation.rooms.service import RoomService
            from meshcorestation.rooms.server import RoomWorker
            service = RoomService(self.room_path)
            selected = service.bot_room()
            self.companion.room_bot_id = selected
            detail = service.config(selected) if selected is not None else {}
            self.companion.room_bot_name = detail.get('name')
            self.companion.room_bot_public_key = detail.get('public_key')
            self.room_error = ''
            self.rooms = RoomWorker(self.companion, service, self.handle_room_post)
            self.companion.room_worker = self.rooms
            self.rooms.start()
            return True
        except Exception as exc:
            self.rooms = None
            self.companion.room_worker = None
            self.room_error = str(exc)
            self.logger.warning('Room server unavailable; bot continues: %s', exc)
            return False

    async def handle_room_post(self, room, post, rx):
        if self.companion is None or self.companion.room_bot_id != room:
            return
        text = post.get('text', '')
        command = self.companion.bot.match_command(text)
        if command is None:
            return
        from meshcorestation.storage import reception_store
        identity = reception_store.room_identity(room, post)
        if reception_store.existing(self.database.db, identity) is not None:
            return
        name = await self.companion.room_sender_name(post.get('author'))
        direct = rx.get('path_len') is None
        message = {'message': text, 'raw_text': text, 'name': name,
                   'type': 'room', 'room_id': room,
                   'room_name': self.companion.room_bot_name,
                   'room_public_key': getattr(self.companion, 'room_bot_public_key', None),
                   'sender_public_key': post.get('author'),
                   'sender_timestamp': post.get('sender_timestamp'),
                   'recv_time': rx.get('received_at', time.time()),
                   'path_len': rx.get('path_len'),
                   'path_hash_mode': rx['path_hash_size'] - 1 if isinstance(rx.get('path_hash_size'), int) else None,
                   'path': 'direct' if direct else f"{rx['path_len']} hops",
                   'command_status': 'processing'}
        self.logger.info("%s | room=%r | sender=%r", command['trigger'], self.companion.room_bot_name, name)
        # The regular channel handler already logs through this table. Use the
        # same history for authenticated room messages, not the room posts table.
        command_id = self.database.add_logger(message, rx, rx.get('room_scope_name') or 'unknown', '')
        reception_store.bind(self.database.db, identity, command_id, 'room')
        from meshcorestation.commands.delivery import ReplyDelivery
        delivery = ReplyDelivery()

        async def send(part):
            post = self.rooms.service.local_post(room, part)
            from meshcorestation.storage import reply_store
            reply_store.room_reply(self.database.db, command_id, room, self.companion.room_bot_name, part,
                                   post['timestamp'] if isinstance(post, dict) else int(time.time()))
            return part

        try:
            reply = await self.companion.bot.handle_message(message, rx, command)
            await delivery.deliver(reply, send)
        except BaseException:
            delivery.failed()
            raise
        finally:
            with self.database.db:
                self.database.db.execute(
                    'UPDATE logger SET reply=?,command_status=? WHERE id=?',
                    (delivery.text, delivery.status, command_id))

    async def session(self):
        self.companion = Companion(self.logger, self.database)
        self.companion.statistics = self.statistics
        if not await self.companion.connect():
            raise ConnectionError('No response from companion')
        try:
            event = await self.companion.mc.commands.send_device_query()
            self.device_info = {key: event.payload.get(key) for key in ('ver', 'model', 'fw_build')}
        except Exception:
            self.device_info = {}
        self.companion.device_info = self.device_info
        await self.companion.subscribe()
        self.statistics.connected = True
        self.control = CompanionControl(self.companion)
        self.voltage = VoltageMonitor(self.companion)
        self.voltage.start()
        self.neighbor_monitor.start()
        await self.start_rooms()
        self.logger.set_log_level()
        while True:
            connected = self.companion.mc.connection_manager.is_connected
            if not connected:
                self.companion.reply_retries.cancel('Companion disconnected; pending retries cancelled.')
                raise ConnectionError('Companion connection lost')
            bridge.status = ('Running', 'MeshcoreStation companion connected', 'running') if connected else ('Reconnecting', 'Companion connection lost', 'unknown')
            await asyncio.sleep(1)

    async def run(self):
        self.statistics.start()
        bridge.attach(self)
        try:
            while True:
                self.reconnect_requested.clear()
                bridge.status = ('Connecting', 'Opening the selected serial port', 'unknown')
                session = asyncio.create_task(self.session(), name='radio-session')
                reconnect = asyncio.create_task(self.reconnect_requested.wait())
                try:
                    done, _ = await asyncio.wait({session, reconnect}, return_when=asyncio.FIRST_COMPLETED)
                    if session in done:
                        await session
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    bridge.status = ('Offline', 'Check serial port in Settings', 'stopped')
                    self.logger.warning('Companion offline: %s', exc)
                finally:
                    session.cancel()
                    reconnect.cancel()
                    await asyncio.gather(session, reconnect, return_exceptions=True)
                    await self.close_session()
                if not self.reconnect_requested.is_set():
                    try:
                        await asyncio.wait_for(self.reconnect_requested.wait(), timeout=10)
                    except asyncio.TimeoutError:
                        pass
        finally:
            await self.statistics.close()
            bridge.detach()
