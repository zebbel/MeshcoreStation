"""Read-only recording health, independent of UI/telemetry collection controls."""
import sqlite3
from flask import jsonify, request
from meshcorestation import config
from meshcorestation.bridge import bridge
from meshcorestation.storage import passive_stats


def register_statistics_routes(server):
    @server.get('/api/repeater-statistics/status')
    def statistics_status():
        try:
            value = passive_stats.snapshot(config.DB_PATH, request.args.get('public_key') or None)
            runtime = bridge.runtime
            collector = getattr(runtime, 'statistics', None)
            value['health'] = collector.health(value['selected']) if collector else dict(
                running=False, connected=False, queued=0, dropped=0, invalid=0,
                error='Statistics collector is not running.', repeater_error='', last_write=None)
            return jsonify(value)
        except ValueError as exc:
            return jsonify(ok=False,error=str(exc)),400
        except (OSError,sqlite3.Error):
            return jsonify(ok=False,error='Recording status unavailable. Saved history has not been deleted.'),503
