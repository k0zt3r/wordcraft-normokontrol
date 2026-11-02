"""Opt-in personal details and a local formatting dialog; no network storage."""
import json
from pathlib import Path
from atomic_files import write_json
from format_profile import ROOT, LOCAL_PATH, PROFILE, BOUNDS, validate

SETTINGS_PATH=ROOT/'.normokontrol-settings.json'


def load(path=SETTINGS_PATH):
    try:
        data=json.loads(Path(path).read_text(encoding='utf-8'))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):
        return {}


def save(details, remember, path=SETTINGS_PATH):
    if remember:
        write_json(path,{'remember':True,'details':details})
    else:
        Path(path).unlink(missing_ok=True)


def profile_dialog(root):
    import tkinter as tk
    from tkinter import ttk,messagebox
    dialog=tk.Toplevel(root)
    dialog.title('Параметры оформления')
    dialog.transient(root)
    dialog.grab_set()
    labels={'text_size':'Кегль основного текста','line_spacing':'Межстрочный интервал',
            'body_indent_mm':'Абзац, мм','compact_indent_mm':'Абзац обычной работы, мм',
            'chapter_gap_pt':'После главы, пт','subheading_gap_pt':'После подзаголовка, пт',
            'stamp_size':'Надписи штампа, пт','stamp_code_size':'Шифр в штампе, пт',
            'frame_stroke_pt':'Толщина рамки, пт'}
    values={}
    for row,(key,label) in enumerate(labels.items()):
        ttk.Label(dialog,text=label).grid(row=row,column=0,sticky='w',padx=12,pady=4)
        values[key]=tk.StringVar(value=str(PROFILE[key]))
        ttk.Entry(dialog,textvariable=values[key],width=10).grid(row=row,column=1,padx=12,pady=4)
    ttk.Label(dialog,text='Изменения применятся после перезапуска.\nЭто локальные настройки; они могут отличаться от положения.',wraplength=440).grid(row=len(labels),column=0,columnspan=2,padx=12,pady=10)
    def apply():
        try:
            data={key:float(value.get().replace(',','.')) for key,value in values.items()}
            validate(dict(PROFILE,**data))
            write_json(LOCAL_PATH,data)
        except (ValueError,OSError) as error:
            messagebox.showerror('Параметры оформления',str(error),parent=dialog)
            return
        messagebox.showinfo('Сохранено','Перезапустите программу, чтобы применить параметры.',parent=dialog)
        dialog.destroy()
    ttk.Button(dialog,text='Сохранить',command=apply).grid(row=len(labels)+1,column=0,padx=12,pady=12)
    ttk.Button(dialog,text='Закрыть',command=dialog.destroy).grid(row=len(labels)+1,column=1,padx=12,pady=12)
