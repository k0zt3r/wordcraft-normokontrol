"""Local Tk interface for the standalone Wordcraft normalisation tool."""
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from irgups_data import UNIVERSITY_FULL, UNIVERSITY_SHORT, DIRECTORY, WORK_TYPES, DOCUMENT_CODES, unit_code, generate_number


def install_edit_shortcuts(root):
    """Windows keycodes stay stable when the active keyboard layout is Russian."""
    actions = {65: '<<SelectAll>>', 67: '<<Copy>>', 86: '<<Paste>>', 88: '<<Cut>>', 90: '<<Undo>>'}
    editable = ('Entry', 'TEntry', 'Text', 'TCombobox', 'Spinbox', 'TSpinbox')

    def invoke(widget, action):
        if action == '<<SelectAll>>':
            if widget.winfo_class() == 'Text':
                widget.tag_add('sel', '1.0', 'end-1c')
            else:
                widget.selection_range(0, 'end')
            return
        try:
            widget.event_generate(action)
        except tk.TclError:
            pass  # Empty undo stack or unsupported action.

    def shortcut(event):
        action = actions.get(event.keycode) if os.name == 'nt' else None
        if action and event.state & 4 and not event.state & 8:
            invoke(event.widget, action)
            return 'break'

    menu = tk.Menu(root, tearoff=False)
    def popup(event):
        widget = event.widget
        widget.focus_set()
        menu.delete(0, 'end')
        for label, action in [('Копировать', '<<Copy>>'), ('Вставить', '<<Paste>>'),
                              ('Вырезать', '<<Cut>>'), ('Выделить всё', '<<SelectAll>>')]:
            menu.add_command(label=label, command=lambda a=action: invoke(widget, a))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return 'break'

    # Run before widget class bindings to prevent a second paste on Latin layouts.
    root.bind_class('NormokontrolEdit', '<KeyPress>', shortcut)
    root.bind_class('NormokontrolEdit', '<Button-3>', popup)
    def attach(widget):
        if widget.winfo_class() in editable:
            widget.bindtags(('NormokontrolEdit',) + widget.bindtags())
        for child in widget.winfo_children():
            attach(child)
    attach(root)


def show(process, create_document, initial=None):
    root = tk.Tk()
    root.title("Нормоконтроль ИрГУПС · Wordcraft")
    root.geometry("1000x760")
    root.minsize(820, 600)
    root.option_add("*Font", "{Segoe UI} 10")
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background='#f4f6fa', foreground='#233047')
    style.configure('TEntry', fieldbackground='white', padding=6)
    style.configure('TCombobox', fieldbackground='white', padding=5)
    style.configure('Accent.TButton', background='#245edb', foreground='white', font=('Segoe UI', 11, 'bold'))
    style.map('Accent.TButton', background=[('disabled', '#b5c3dd'), ('active', '#194ab5')])
    style.configure('Subtitle.TLabel', foreground='#56657d', font=('Segoe UI', 11))
    style.configure('TButton', padding=(12, 7))
    style.configure('TNotebook.Tab', padding=(14, 8))
    style.configure('Title.TLabel', font=('Segoe UI', 17, 'bold'))
    pane = ttk.Frame(root, padding=20)
    pane.pack(fill="both", expand=True)
    source = tk.StringVar(value=str(initial or ""))
    new = tk.BooleanVar(value=False)
    formatting = tk.BooleanVar(value=True)
    check = tk.BooleanVar(value=False)
    toc_option = tk.BooleanVar(value=False)
    bibliography = tk.BooleanVar(value=False)
    status = tk.StringVar(value="Выберите DOCX или создайте новый документ. Все поля необязательные.")
    fields = (("author", "Фамилия И.О. студента"), ("group", "Группа"),
              ("supervisor", "Фамилия И.О. преподавателя"), ("supervisor_title", "Должность / регалии"),
              ("work_type", "Вид работы"), ("discipline", "Дисциплина"),
              ("title", "Название работы / тема"), ("code", "Шифр работы"),
              ("city", "Город"), ("year", "Год"),
              ("faculty", "Факультет"), ("department", "Кафедра"),
              ("stamp_title", "Краткое название в штампе"))
    details = {key: tk.StringVar() for key, _ in fields}
    approval = tk.BooleanVar(value=False)
    approval_person, approval_title = tk.StringVar(), tk.StringVar()
    extra_sections = {key:tk.BooleanVar(value=False) for key in ('annotation','normative','abbreviations')}
    reg = {key:tk.StringVar(value=value) for key,value in (('work_code','КР'),('division_code',''),('specialty',''),('account',''),('document_code','ПЗ'))}
    include_year = tk.BooleanVar(value=False)
    def browse():
        path = filedialog.askopenfilename(title="Выберите работу", filetypes=[("Документ Word", "*.docx")])
        if path:
            new.set(False)
            source.set(path)
    def blank():
        new.set(True)
        check.set(False)
        source.set("Новый документ — титульник и выбранные заготовки")
    ttk.Label(pane, text="Нормоконтроль ИрГУПС", style='Title.TLabel').grid(row=0, column=0, sticky="w", pady=(0, 8))
    ttk.Entry(pane, textvariable=source, state='readonly').grid(row=1, column=0, sticky="ew", pady=(4, 12))
    ttk.Button(pane, text="Выбрать документ…", command=browse).grid(row=1, column=1, padx=8, pady=(4, 12))
    ttk.Button(pane, text="Новый документ", command=blank).grid(row=1, column=2, pady=(4, 12))
    ttk.Label(pane, text="Подготовьте работу к сдаче: оформление, рамки и проверка замечаний.", style='Subtitle.TLabel').grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 14))
    notebook = ttk.Notebook(pane)
    notebook.grid(row=5, column=0, columnspan=3, sticky="nsew")
    def page(label):
        outer = ttk.Frame(notebook)
        notebook.add(outer, text=label)
        canvas = tk.Canvas(outer, highlightthickness=0, background='#f4f6fa')
        scroll = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        content = ttk.Frame(canvas, padding=20)
        window = canvas.create_window((0, 0), window=content, anchor='nw')
        content.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))
        return content
    home_tab = page('Начать')
    title_tab = page('Данные работы')
    reg_tab = page('Шифр работы')
    toc_tab = page('Содержание')
    ref_tab = page('Источники')
    ttk.Label(home_tab, text='1. Выберите документ или создайте новый', style='Title.TLabel').pack(anchor='w', pady=(0, 8))
    ttk.Label(home_tab, text='Кнопки выбора находятся сверху. Поддерживаются файлы .docx.', wraplength=700).pack(anchor='w')
    ttk.Label(home_tab, text='2. Что нужно сделать?', style='Title.TLabel').pack(anchor='w', pady=(24, 10))
    ttk.Radiobutton(home_tab, text='Оформить и проверить', variable=check, value=False).pack(anchor='w', pady=5)
    ttk.Label(home_tab, text='Добавить рамки и штампы, привести текст и таблицы к требованиям, проверить результат.', wraplength=700, style='Subtitle.TLabel').pack(anchor='w', padx=24)
    ttk.Radiobutton(home_tab, text='Только найти замечания', variable=check, value=True).pack(anchor='w', pady=(16, 5))
    ttk.Label(home_tab, text='Получить отчёт без исправления оформления. Подходит для готовой работы.', wraplength=700, style='Subtitle.TLabel').pack(anchor='w', padx=24)
    ttk.Label(home_tab, text='3. Запустите обработку', style='Title.TLabel').pack(anchor='w', pady=(24, 8))
    ttk.Label(home_tab, text='Для обычной проверки больше ничего заполнять не нужно. Данные титульника и заготовки можно указать на соседних вкладках.', wraplength=700).pack(anchor='w')
    ttk.Checkbutton(home_tab, text='Исправлять шрифт, интервалы и оформление таблиц', variable=formatting).pack(anchor='w', pady=(20, 0))
    ttk.Label(title_tab, text="Заполните нужное. Пустое поле сохраняет исходное значение; в новом документе остаётся пустым.", wraplength=860).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))
    ttk.Label(title_tab, text=UNIVERSITY_FULL+'\n('+UNIVERSITY_SHORT+')', wraplength=860, foreground='#4b5968').grid(row=1,column=0,columnspan=4,sticky='w',pady=(0,8))
    for n, (key, label) in enumerate(fields):
        row, col = n // 2 + 3, n % 2 * 2
        ttk.Label(title_tab, text=label).grid(row=row, column=col, sticky="w", padx=(10 if col else 0, 8), pady=6)
        if key == "work_type":
            widget = ttk.Combobox(title_tab, textvariable=details[key], values=tuple(WORK_TYPES.values()), width=22)
        elif key=='faculty':
            widget=ttk.Combobox(title_tab,textvariable=details[key],values=tuple(DIRECTORY),width=22)
            faculty_picker=widget
        elif key=='department':
            widget=ttk.Combobox(title_tab,textvariable=details[key],values=tuple(name for rows in DIRECTORY.values() for name,_ in rows),width=22)
            department_picker=widget
        else:
            widget = ttk.Entry(title_tab, textvariable=details[key], width=22)
        widget.grid(row=row, column=col + 1, sticky="ew", pady=6)
    title_tab.columnconfigure(1, weight=1)
    title_tab.columnconfigure(3, weight=1)
    last_row=(len(fields)-1)//2+4
    ttk.Checkbutton(title_tab,text='Добавить гриф «К защите допускаю» (§6.2д)',variable=approval).grid(row=last_row,column=0,columnspan=4,sticky='w',pady=(6,0))
    for row,(text,var) in enumerate((('Фамилия И.О. допускающего',approval_person),('Должность / регалии допускающего',approval_title)),last_row+1):
        ttk.Label(title_tab,text=text).grid(row=row,column=0,columnspan=2,sticky='w',pady=4)
        ttk.Entry(title_tab,textvariable=var).grid(row=row,column=2,columnspan=2,sticky='ew',pady=4)

    ttk.Label(reg_tab,text='По §6.2: учебные работы — без учётного номера; ВКР — с номером кафедры и годом. Код подразделения — 6 цифр. Длина шифра не фиксирована.',wraplength=860).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,12))
    entries=(('Вид работы',reg['work_code'],tuple(WORK_TYPES)),('Код подразделения',reg['division_code'],None),
             ('Направление / специальность (10.03.01)',reg['specialty'],None),('Учётный номер ВКР (например 001)',reg['account'],None),
             ('Год (также для титульника)',details['year'],None),('Шифр документа',reg['document_code'],tuple(DOCUMENT_CODES)))
    for row,(label,var,values) in enumerate(entries,1):
        ttk.Label(reg_tab,text=label).grid(row=row,column=0,sticky='w',pady=5,padx=(0,18))
        w=ttk.Combobox(reg_tab,textvariable=var,values=values,state='readonly') if values else ttk.Entry(reg_tab,textvariable=var)
        w.grid(row=row,column=1,sticky='ew',pady=5)
    ttk.Checkbutton(reg_tab,text='Добавлять год в учебный шифр — только по кафедральному образцу',variable=include_year).grid(row=7,column=0,columnspan=2,sticky='w',pady=8)
    reg_hint=tk.StringVar(value='Коды кафедр взяты из приложения А (2017), названия — с официального сайта. Для новых / переименованных кафедр неподтверждённый код не подставляется.')
    ttk.Label(reg_tab,textvariable=reg_hint,wraplength=860,foreground='#596574').grid(row=8,column=0,columnspan=2,sticky='w',pady=6)
    preview=tk.StringVar()
    def number():
        account=reg['account'].get() if reg['work_code'].get() in {'ДП','ДР','МД'} else ''
        return generate_number(reg['work_code'].get(),reg['division_code'].get(),reg['specialty'].get(),reg['document_code'].get(),account,details['year'].get(),include_year.get())
    def refresh(*_):
        try:
            value=number(); preview.set(f'{value}  ({len(value)} символов)')
        except ValueError as error:
            preview.set(str(error))
    def apply_number():
        try:
            details['code'].set(number())
            details['work_type'].set(WORK_TYPES[reg['work_code'].get()])
            status.set('Шифр вставлен в поля титульника и штампа.')
        except ValueError as error:
            messagebox.showinfo('Генератор номера',str(error))
    for var in (*reg.values(),details['year'],include_year): var.trace_add('write',refresh)
    ttk.Label(reg_tab,textvariable=preview,wraplength=860).grid(row=9,column=0,columnspan=2,sticky='w',pady=8)
    ttk.Button(reg_tab,text='Вставить номер в титульник и штамп',command=apply_number).grid(row=10,column=0,columnspan=2,sticky='ew')
    reg_tab.columnconfigure(1,weight=1)
    def select_department(*_):
        code=unit_code(details['department'].get())
        parent=next((name for name,rows in DIRECTORY.items() if any(d==details['department'].get() for d,_ in rows)),None)
        if parent:
            details['faculty'].set(parent)
            department_picker.configure(values=tuple(d for d,_ in DIRECTORY[parent]))
        reg['division_code'].set(code or '')
        reg_hint.set(f'Код {code} — приложение А, 2017 г.; при изменении кода кафедры исправьте его вручную.' if code else 'В приложении А нет надёжно сопоставленного кода этой кафедры. Введите подтверждённый код вручную.')
    def select_faculty(*_):
        names=tuple(name for name,_ in DIRECTORY.get(details['faculty'].get(),[]))
        department_picker.configure(values=names)
        if details['department'].get() not in names:
            details['department'].set(''); reg['division_code'].set('')
    faculty_picker.bind('<<ComboboxSelected>>',select_faculty)
    department_picker.bind('<<ComboboxSelected>>',select_department)
    def sync_work(*_):
        code=next((code for code,title in WORK_TYPES.items() if title==details['work_type'].get()),None)
        if code: reg['work_code'].set(code)
    details['work_type'].trace_add('write',sync_work)
    refresh()
    ttk.Checkbutton(toc_tab, text="Создать содержание — таблица из курсача", variable=toc_option).pack(anchor="w")
    for key,label in (('annotation','Аннотация'),('normative','Нормативные ссылки'),('abbreviations','Обозначения и сокращения')):
        ttk.Checkbutton(toc_tab,text='Добавить заготовку: '+label,variable=extra_sections[key]).pack(anchor='w')
    ttk.Label(toc_tab, text="Можно оставить пустым — получите пустую таблицу. Или введите по одному заголовку на строку, например:\nВведение\n1 Теоретическая часть\n1.1 Основные понятия\nЗаключение\nСписок использованных источников", wraplength=850).pack(anchor="w", pady=10)
    toc_text = tk.Text(toc_tab, height=9, wrap="word", undo=True)
    toc_text.pack(fill="both", expand=True)
    ttk.Label(toc_tab, text="Номера страниц определятся по существующим заголовкам. Отсутствующие разделы будут отмечены в отчёте.", wraplength=850).pack(anchor="w", pady=(8, 0))
    ttk.Checkbutton(ref_tab, text="Создать список литературы — таблица из курсача", variable=bibliography).pack(anchor="w")
    ttk.Label(ref_tab, text="Без текста — пустая таблица. Для заполнения введите по одному описанию источника на строку.\nНумерация добавляется автоматически, без точки. Не вводите номер перед описанием.", wraplength=850).pack(anchor="w", pady=10)
    ref_text = tk.Text(ref_tab, height=10, wrap="word", undo=True)
    ref_text.pack(fill="both", expand=True)
    ttk.Label(ref_tab, text="Скрипт оформляет таблицу по нормоконтролю. Недостающих авторов, дат, страниц и адресов он не выдумывает.", wraplength=850).pack(anchor="w", pady=(8, 0))
    ttk.Label(pane, text="Результат сохранится в отдельную папку. Исходная работа останется у вас.", foreground="#596574").grid(row=6, column=0, columnspan=3, sticky="w", pady=(12, 0))
    bar = ttk.Progressbar(pane, mode="indeterminate")
    bar.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(12, 8))
    ttk.Label(pane, textvariable=status, wraplength=900).grid(row=8, column=0, columnspan=3, sticky="w")
    events = queue.Queue()
    def run():
        if new.get() and check.get():
            messagebox.showinfo("Нормоконтроль", "Для нового документа отключите режим «Только проверить».")
            return
        if not source.get():
            browse()
        if not source.get():
            return
        creating = new.get()
        out = None
        if creating:
            selected = filedialog.askdirectory(title="Куда сохранить новую работу?")
            if not selected:
                return
            from datetime import datetime
            out = Path(selected) / f"Новая_работа_{datetime.now():%Y%m%d_%H%M%S}"
        input_path = source.get()
        options = dict(format_text=formatting.get(), check_only=check.get(), metadata={k: v.get().strip() for k, v in details.items()},
                       toc_template=toc_option.get(), bibliography_template=bibliography.get(),
                       toc_entries=[s.strip() for s in toc_text.get("1.0", "end").splitlines() if s.strip()],
                       bibliography_entries=[s.strip() for s in ref_text.get("1.0", "end").splitlines() if s.strip()])
        options['metadata'].update({'approval':approval.get(),'approval_person':approval_person.get().strip(),'approval_title':approval_title.get().strip()})
        options['optional_sections']=[key for key,var in extra_sections.items() if var.get()]
        button.configure(state="disabled")
        bar.start(15)
        def worker():
            try:
                progress = lambda m: events.put(("status", m))
                result = create_document(out, progress=progress, **options) if creating else process(input_path, progress=progress, **options)
                events.put(("done", result))
            except Exception as error:
                events.put(("error", str(error)))
        threading.Thread(target=worker, daemon=True).start()
    button = ttk.Button(pane, text="Оформить и проверить", command=run, style='Accent.TButton')
    button.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(12, 0))
    pane.columnconfigure(0, weight=1)
    pane.rowconfigure(5, weight=1)
    result_path = None
    result_bar = ttk.Frame(pane)
    result_bar.grid(row=10, column=0, columnspan=3, sticky='ew', pady=(8, 0))
    def open_result(name=None):
        if result_path:
            try:
                os.startfile(str(result_path / name if name else result_path))
            except OSError as error:
                messagebox.showerror('Не удалось открыть результат', str(error))
    report_button = ttk.Button(result_bar, text='Посмотреть замечания', command=lambda: open_result('report.html'), state='disabled')
    report_button.pack(side='left')
    folder_button = ttk.Button(result_bar, text='Открыть папку с документами', command=open_result, state='disabled')
    folder_button.pack(side='left', padx=8)
    def mode_changed(*_):
        button.configure(text='Проверить работу' if check.get() else 'Оформить и проверить')
        for tab in notebook.tabs()[1:]:
            notebook.tab(tab, state='disabled' if check.get() else 'normal')
        if check.get():
            notebook.select(0)
    check.trace_add('write', mode_changed)
    def close():
        if str(button.cget("state")) == "disabled":
            status.set("Дождитесь завершения обработки документа.")
        else:
            root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    def poll():
        nonlocal result_path
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == "status":
                    status.set(value)
                else:
                    bar.stop()
                    button.configure(state="normal")
                    if kind == "error":
                        status.set("Не удалось завершить. Исходник не изменён.")
                        messagebox.showerror("Нормоконтроль", value)
                    else:
                        count = len(value['issues'])
                        status.set(f"Работа обработана: {value['pages']} стр. Замечаний для просмотра: {count}." if count else 'Обработка завершена. Автоматических замечаний нет — просмотрите документы перед сдачей.')
                        result_path = Path(value['output'])
                        report_button.configure(state='normal')
                        folder_button.configure(state='normal')
        except queue.Empty:
            pass
        root.after(150, poll)
    root.after(150, poll)
    install_edit_shortcuts(root)
    root.mainloop()
