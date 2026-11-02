"""Real Tk clipboard smoke test; run in a desktop user session."""
import tkinter as tk
import unittest
from tkinter import ttk
from normokontrol_gui import install_edit_shortcuts


class ClipboardTests(unittest.TestCase):
    def test_main_window_has_result_controls_and_scrollable_title(self):
        from unittest.mock import patch
        import normokontrol_gui as gui
        original=tk.Tk
        roots=[]
        def create():
            root=original()
            root.withdraw()
            root.mainloop=lambda:None
            roots.append(root)
            return root
        try:
            with patch.object(gui.tk,'Tk',create):
                gui.show(None,None)
            root=roots[0]
            def children(widget):
                yield widget
                for child in widget.winfo_children():
                    yield from children(child)
            widgets=list(children(root))
            texts={w.cget('text') for w in widgets if w.winfo_class()=='TButton'}
            self.assertTrue({'DOCX','PDF','Папка','Отмена','Оформление'} <= texts)
            self.assertTrue(any(w.winfo_class()=='Canvas' for w in widgets))
        finally:
            for root in roots:
                root.destroy()

    def test_clipboard_entry_and_multiline(self):
        root = tk.Tk()
        root.withdraw()
        try:
            entry = ttk.Entry(root)
            text = tk.Text(root, undo=True)
            install_edit_shortcuts(root)
            # Invoke the same pre-class binding used for physical Ctrl shortcuts,
            # supplying a Cyrillic keysym and Windows physical keycode.
            from types import SimpleNamespace
            binding = root.bind_class('NormokontrolEdit', '<KeyPress>')
            self.assertTrue(binding)
            for widget in (entry, text):
                widget.insert('1.0' if widget == text else 0, 'Проверка')
                def key(code):
                    widget.event_generate('<KeyPress>', keycode=code, state=4)
                    root.update()
                root.deiconify()
                widget.pack()
                root.update()
                widget.focus_force()
                root.update()
                key(65)
                key(67)
                self.assertEqual(root.clipboard_get(), 'Проверка')
                key(88)
                key(86)
                value = widget.get('1.0', 'end-1c') if widget == text else widget.get()
                self.assertEqual(value, 'Проверка')
                widget.pack_forget()
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
