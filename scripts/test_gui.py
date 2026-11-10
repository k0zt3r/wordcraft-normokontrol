"""Real Tk clipboard smoke test; run in a desktop user session."""
import tkinter as tk
import unittest
from tkinter import ttk
from normokontrol_gui import install_edit_shortcuts


class ClipboardTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        self.callback_errors = []
        callbacks = patch.object(tk.Tk, 'report_callback_exception',
                                 lambda root, *error: self.callback_errors.append(error))
        callbacks.start()
        self.addCleanup(callbacks.stop)
        self.addCleanup(lambda: self.assertEqual(self.callback_errors, [],
                                                'Tk callbacks raised exceptions'))

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
            self.assertTrue({'Открыть папку','Отмена','Оформление'} <= texts)
            self.assertFalse({'DOCX','PDF','Папка'} & texts)
            folder=next(w for w in widgets if w.winfo_class()=='TButton' and w.cget('text')=='Открыть папку')
            self.assertTrue(folder.instate(['disabled']))
            choices=[w for w in widgets if w.winfo_class()=='TRadiobutton']
            self.assertEqual({w.cget('value') for w in choices},{'new','preserve'})
            self.assertEqual(root.getvar(choices[0].cget('variable')),'new')
            check_only=next(w for w in widgets if w.winfo_class()=='TCheckbutton'
                            and w.cget('text').startswith('Только проверить'))
            check_only.invoke()
            self.assertTrue(all(w.instate(['disabled']) for w in choices))
            check_only.invoke()
            self.assertTrue(all(not w.instate(['disabled']) for w in choices))
            self.assertEqual(sum(w.winfo_class() == 'Canvas' for w in widgets), 4)
            editors = [w for w in widgets if w.winfo_class() == 'Text']
            self.assertEqual(len(editors), 2)
            for editor in editors:
                self.assertTrue(editor.cget('yscrollcommand'))
                self.assertTrue(any(w.winfo_class() == 'TScrollbar' for w in editor.master.winfo_children()))
        finally:
            for root in roots:
                for job in root.tk.splitlist(root.tk.call('after', 'info')):
                    root.after_cancel(job)
                root.destroy()

    def test_window_fits_2k_screen_at_common_dpi_scales(self):
        from unittest.mock import patch
        import normokontrol_gui as gui
        original = tk.Tk
        for screen_w, screen_h, scale in ((1366, 768, 1.0), (1366, 768, 1.5),
                                         (2560, 1440, 1.0), (2560, 1440, 1.25),
                                         (2560, 1440, 1.5), (2560, 1440, 2.0)):
            with self.subTest(screen=(screen_w, screen_h), scale=scale):
                roots = []
                def create():
                    root = original()
                    root.withdraw()
                    root.tk.call('tk', 'scaling', 96 * scale / 72)
                    root.winfo_fpixels = lambda unit: 96 * scale
                    root.winfo_screenwidth = lambda: screen_w
                    root.winfo_screenheight = lambda: screen_h
                    root.mainloop = lambda: None
                    roots.append(root)
                    return root
                try:
                    with patch.object(gui.tk, 'Tk', create):
                        gui.show(None, None)
                    root = roots[0]
                    root.deiconify()
                    root.update()
                    self.assertLessEqual(root.winfo_width(), screen_w)
                    self.assertLessEqual(root.winfo_height(), screen_h)
                    self.assertLessEqual(root.minsize()[0], root.winfo_width())
                    self.assertLessEqual(root.minsize()[1], root.winfo_height())
                    def visit(widget):
                        yield widget
                        for child in widget.winfo_children():
                            yield from visit(child)
                    run = next(w for w in visit(root) if w.winfo_class() == 'TButton'
                               and w.cget('text').startswith('Выполнить'))
                    self.assertGreater(run.winfo_height(), 0)
                    self.assertLessEqual(run.winfo_rooty() + run.winfo_height(),
                                         root.winfo_rooty() + root.winfo_height())
                    notebook = next(w for w in visit(root) if w.winfo_class() == 'TNotebook')
                    for tab in notebook.tabs():
                        notebook.select(tab)
                        root.update()
                        canvas = next(w for w in visit(root.nametowidget(tab))
                                      if w.winfo_class() == 'Canvas')
                        self.assertGreater(canvas.winfo_height(), 0)
                        canvas.yview_moveto(1)
                        root.update()
                        self.assertAlmostEqual(canvas.yview()[1], 1)
                        for editor in (w for w in visit(canvas) if w.winfo_class() == 'Text'):
                            editor.insert('1.0', '\n'.join(str(i) for i in range(200)))
                            editor.yview_moveto(1)
                            root.update()
                            self.assertAlmostEqual(editor.yview()[1], 1)
                finally:
                    for root in roots:
                        for job in root.tk.splitlist(root.tk.call('after', 'info')):
                            root.after_cancel(job)
                        root.destroy()

    def test_clipboard_entry_and_multiline(self):
        import os
        if os.name != 'nt':
            self.skipTest('Physical Windows keycodes; native bindings are used on Linux.')
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

    def test_small_viewport_reaches_last_field_and_long_text(self):
        from normokontrol_gui import scrollable_form, text_editor
        root = tk.Tk()
        try:
            root.geometry('420x180')
            shell = ttk.Frame(root)
            shell.pack(fill='both', expand=True)
            form = scrollable_form(shell, 120, 380)
            ttk.Label(form, text='Инструкция ' * 30, wraplength=800).pack(fill='x')
            editor = text_editor(form, 9)
            editor.insert('1.0', '\n'.join(f'Источник {i}' for i in range(200)))
            last = ttk.Label(form, text='Последнее поле')
            last.pack()
            root.update()
            canvas = form.master
            self.assertLess(canvas.yview()[1], 1)
            canvas.yview_moveto(1)
            root.update()
            self.assertGreaterEqual(last.winfo_rooty(), canvas.winfo_rooty())
            self.assertLessEqual(last.winfo_rooty() + last.winfo_height(), canvas.winfo_rooty() + canvas.winfo_height())
            editor.yview_moveto(1)
            self.assertAlmostEqual(editor.yview()[1], 1)
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
