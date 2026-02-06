# tx2tx Pointer Provider (GNOME Shell Extension)

This GNOME Shell extension exposes the global pointer position over DBus so
`tx2tx` can obtain accurate cursor coordinates on Wayland.

## Install (local)

```bash
mkdir -p ~/.local/share/gnome-shell/extensions
cp -r gnome-extension/tx2tx-pointer@tx2tx ~/.local/share/gnome-shell/extensions/
```

Then enable:

```bash
gnome-extensions enable tx2tx-pointer@tx2tx
```

Restart GNOME Shell if needed (on X11: `Alt+F2`, then `r`, Enter).
On Wayland, log out/in.

## Verify

```bash
gdbus call --session \
  --dest org.tx2tx.Pointer \
  --object-path /org/tx2tx/Pointer \
  --method org.tx2tx.Pointer.GetPointer
```

You should see `(int32 X, int32 Y)`.
