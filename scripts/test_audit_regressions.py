import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from docx import Document
import normokontrol as nk
from document_cleanup import prepare
from integrity import check_import, preserving
from rules_checks import check_rules
from structure import analyze
from test_rules_checks import paragraph as p


class AuditTests(unittest.TestCase):
    def test_import_loss_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.docx'
            doc=Document();doc.add_paragraph('Protected original text.');doc.save(path)
            check_import(path,{'body':[p('Protected original text.')]})
            with self.assertRaises(RuntimeError):
                check_import(path,{'body':[p('Lost text.')]})

    def test_transformation_loss_is_detected(self):
        model={'body':[p('Protected text')],'styles':{}}
        def lose(model):
            model['body'].clear()
        with self.assertRaises(RuntimeError):
            preserving(model,lose)

    def test_numbered_sources_and_continuation(self):
        model={'body':[p('Введение'),p('Список использованных источников'),
                       p('1. Первый источник.'),p('Продолжение первого источника.'),p('2. Второй источник.')], 'styles':{}}
        preserving(model,prepare,[],[])
        rows=model['body'][-1]['rows']
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['cells'][1]['blocks'][0]['text'],'Первый источник.')
        self.assertEqual(len(rows[0]['cells'][1]['blocks']),2)

    def test_ambiguous_sources_left_unchanged(self):
        model={'body':[p('Введение'),p('Список литературы'),p('Непонятное описание'),p('Его продолжение')], 'styles':{}}
        original=copy.deepcopy(model);issues=[]
        prepare(model,[],issues)
        self.assertEqual(model,original)
        self.assertIn('bibliography-review',{i['code'] for i in issues})

    def test_chapter_and_subsection_share_structure(self):
        model={'body':[p('Глава 1. Теория',spaceAfter=28),p('1.1 Подраздел')], 'styles':{}}
        issues=[];check_rules(model,'full',issues)
        self.assertNotIn('heading-parent',{i['code'] for i in issues})
        self.assertEqual(analyze({'body':[p('1 Первый пункт')],'styles':{}})['levels'],{})

    def test_reference_scan_does_not_rescan_toc_per_paragraph(self):
        model={'body':[p('Введение')]+[p('Рисунок '+str(i)+' — Название') if i%10==0 else p('Текст') for i in range(200)],'styles':{}}
        with patch.object(nk,'detect_tocs',wraps=nk.detect_tocs) as scan:
            nk.structural_checks(None,model,'compact',[])
            self.assertLess(scan.call_count,25)

    def test_framed_blank_page_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            doc=Document();doc.add_heading('Введение',1);doc.add_paragraph('Body text.')
            doc.add_page_break();doc.add_page_break();doc.add_paragraph('More text.')
            source=root/'source.docx';doc.save(source)
            report=nk.process(source,root/'out',progress=lambda _:None)
            self.assertIn('empty-page',{i['code'] for i in report['issues']})

    def test_bundle_rollback_on_existing_file(self):
        from atomic_files import publish
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);stage=root/'stage';out=root/'out';stage.mkdir();out.mkdir()
            (stage/'first').write_text('new');(stage/'second').write_text('new')
            (out/'second').write_text('existing')
            with self.assertRaises(FileExistsError):
                publish(stage,out,['first','second'])
            self.assertFalse((out/'first').exists())
            self.assertEqual((out/'second').read_text(),'existing')

    def test_profile_validation(self):
        from format_profile import PROFILE,validate
        for key,value in [('stamp_code_size',100),('text_size',float('nan')),('line_spacing',True)]:
            data=dict(PROFILE);data[key]=value
            with self.assertRaises(ValueError):
                validate(data)


if __name__=='__main__':
    unittest.main()
