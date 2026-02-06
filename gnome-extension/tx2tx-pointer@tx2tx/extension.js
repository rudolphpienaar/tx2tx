const Gio = imports.gi.Gio;

const DBUS_XML = `
<node>
  <interface name="org.tx2tx.Pointer">
    <method name="GetPointer">
      <arg type="i" name="x" direction="out" />
      <arg type="i" name="y" direction="out" />
    </method>
  </interface>
</node>`;

class PointerProvider {
    GetPointer() {
        const [x, y] = global.get_pointer();
        return [x, y];
    }
}

class Tx2txPointerExtension {
    enable() {
        if (this._dbusExport)
            return;

        this._nameId = Gio.bus_own_name(
            Gio.BusType.SESSION,
            'org.tx2tx.Pointer',
            Gio.BusNameOwnerFlags.NONE,
            null,
            null,
            null
        );

        this._dbusExport = Gio.DBusExportedObject.wrapJSObject(DBUS_XML, new PointerProvider());
        this._dbusExport.export(Gio.DBus.session, '/org/tx2tx/Pointer');
    }

    disable() {
        if (this._dbusExport) {
            this._dbusExport.unexport();
            this._dbusExport = null;
        }
        if (this._nameId) {
            Gio.bus_unown_name(this._nameId);
            this._nameId = 0;
        }
    }
}

function init() {
    return new Tx2txPointerExtension();
}
