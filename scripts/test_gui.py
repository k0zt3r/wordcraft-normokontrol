"""Real Tk clipboard smoke test; run in a desktop user session."""
import tkinter as tk
import unittest
from tkinter import ttk
from normokontrol_gui import install_edit_shortcuts


class ClipboardTests(unittest.TestCase):
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
