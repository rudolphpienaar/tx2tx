import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

const DEFAULT_SOCKET_PATH = '/tmp/tx2tx-gnome-truth.sock';
const STREAM_PERIOD_MS = 16;

class TruthBridgeServer {
    constructor(socketPath = DEFAULT_SOCKET_PATH) {
        this._socketPath = socketPath;
        this._service = null;
        this._streamSources = [];
        this._timerId = 0;
    }

    enable() {
        this._socketFile_remove();
        const address = Gio.UnixSocketAddress.new(this._socketPath);
        this._service = new Gio.SocketService();
        this._service.add_address(
            address,
            Gio.SocketType.STREAM,
            Gio.SocketProtocol.DEFAULT,
            null
        );
        this._service.connect('incoming', (service, connection) => {
            this._streamSources.push(connection);
            return true;
        });
        this._service.start();
        this._timerId = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT,
            STREAM_PERIOD_MS,
            () => this._streamTick_emit()
        );
    }

    disable() {
        if (this._timerId > 0) {
            GLib.Source.remove(this._timerId);
            this._timerId = 0;
        }
        for (const connection of this._streamSources) {
            try {
                connection.close(null);
            } catch (e) {
                // Ignore close failures during shutdown.
            }
        }
        this._streamSources = [];
        if (this._service !== null) {
            this._service.stop();
            this._service = null;
        }
        this._socketFile_remove();
    }

    _streamTick_emit() {
        const [x, y] = global.get_pointer();
        const payload = JSON.stringify({
            x,
            y,
            ts: GLib.get_monotonic_time() / 1000000.0,
            focus: global.display.focus_window !== null,
        }) + '\n';
        const nextConnections = [];
        for (const connection of this._streamSources) {
            try {
                const outputStream = connection.get_output_stream();
                outputStream.write_all(payload, null);
                outputStream.flush(null);
                nextConnections.push(connection);
            } catch (e) {
                try {
                    connection.close(null);
                } catch (closeError) {
                    // Ignore close failures for broken streams.
                }
            }
        }
        this._streamSources = nextConnections;
        return GLib.SOURCE_CONTINUE;
    }

    _socketFile_remove() {
        try {
            const file = Gio.File.new_for_path(this._socketPath);
            if (file.query_exists(null)) {
                file.delete(null);
            }
        } catch (e) {
            // Ignore cleanup failures; bind path validation happens in add_address.
        }
    }
}

let bridgeServer = null;

export default class Extension {
    enable() {
        bridgeServer = new TruthBridgeServer();
        bridgeServer.enable();
    }

    disable() {
        if (bridgeServer !== null) {
            bridgeServer.disable();
            bridgeServer = null;
        }
    }
}
