from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, ListFlowable, ListItem

root = Path(__file__).resolve().parents[1]
source_path = root / 'docs' / 'reports' / '원장님_보고용_사이트_사용법_보고서.md'
out_path = root / 'docs' / 'reports' / '원장님_보고용_사이트_사용법_보고서.pdf'

text = source_path.read_text(encoding='utf-8')
lines = [line.rstrip() for line in text.splitlines() if line.strip()]

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='TitleK', parent=styles['Title'], fontName='Helvetica', fontSize=22, leading=28, alignment=TA_CENTER, textColor=colors.HexColor('#0f4c81')))
styles.add(ParagraphStyle(name='BodyK', parent=styles['BodyText'], fontName='Helvetica', fontSize=10.5, leading=15, alignment=TA_LEFT))
styles.add(ParagraphStyle(name='HeadingK', parent=styles['Heading2'], fontName='Helvetica', fontSize=13, leading=18, textColor=colors.HexColor('#0f4c81')))

story = []
for line in lines:
    if line.startswith('# '):
        story.append(Paragraph(line[2:], styles['TitleK']))
        story.append(Spacer(1, 10))
    elif line.startswith('## '):
        story.append(Paragraph(line[3:], styles['HeadingK']))
        story.append(Spacer(1, 6))
    elif line.startswith('- '):
        story.append(ListFlowable([ListItem(Paragraph(line[2:], styles['BodyK']), bulletColor=colors.HexColor('#0f4c81'))]))
    elif line.startswith('1. '):
        story.append(Paragraph(line, styles['BodyK']))
    else:
        story.append(Paragraph(line, styles['BodyK']))
    story.append(Spacer(1, 4))

story.append(Spacer(1, 8))
story.append(Paragraph('생성일: 2026-06-29', styles['BodyK']))

pdf = SimpleDocTemplate(str(out_path), pagesize=A4, title='KIBA 사이트 보고서', author='KIBA')
pdf.build(story)
print(out_path)
