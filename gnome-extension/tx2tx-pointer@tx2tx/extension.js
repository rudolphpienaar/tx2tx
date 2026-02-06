/* exported init enable disable */

const { Gio } = imports.gi;
const Main = imports.ui.main;

const DBUS_XML = `
<node>
  <interface name="org.tx2tx.Pointer">
    <method name="GetPointer">
      <arg type="i" name="x" direction="out" />
      <arg type="i" name="y" direction="out" />
    </method>
  </interface>
</node>`;

let _dbusImpl = null;
let _dbusExport = null;

const PointerProvider = class {
  GetPointer() {
    const [x, y] = global.get_pointer();
    return [x, y];
  }
};

function init() {}

function enable() {
  if (_dbusExport) {
    return;
  }

  _dbusImpl = Gio.DBusExportedObject.wrapJSObject(DBUS_XML, new PointerProvider());
  _dbusImpl.export(Gio.DBus.session, '/org/tx2tx/Pointer');
  _dbusExport = _dbusImpl;
}

function disable() {
  if (_dbusExport) {
    _dbusExport.unexport();
    _dbusExport = null;
  }
  _dbusImpl = null;
}
