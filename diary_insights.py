"""本地 Word 日记词频与时间线。依赖：pip install jieba。"""
import argparse
import collections
import csv
import datetime as dt
import html
import json
import pathlib
import re
import sys
import webbrowser
import zipfile
import xml.etree.ElementTree as ET

STOP = set('我们 你们 他们 自己 一个 一些 这个 那个 这些 那些 然后 但是 因为 所以 如果 觉得 知道 时候 已经 还是 就是 不是 没有 什么 怎么 可以 可能 真的 今天 昨天 明天 一直 现在 这样 那样 还有 只是 比较 非常 特别 有点 一下 一起 起来 开始 最后 后来 其实 不过 而且 对于 以及 进行'.split())
NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
DATE = re.compile(r'(?<!\d)((?:19|20)\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?(?!\d)')


def date_in(text):
    match = DATE.search(text)
    if match:
        try:
            return dt.date(*map(int, match.groups())).isoformat()
        except ValueError:
            pass
    return None


def extract(path):
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
    # 正文与表格，忽略批注、页眉页脚和已删除的修订文字。
    return [
        ''.join(node.text or '' for node in p.iter(NS + 't')).strip()
        for p in root.iter(NS + 'p')
        if any(node.text for node in p.iter(NS + 't'))]


def split_entries(paragraphs, filename):
    result, current = [], []
    date, source = date_in(filename), '文件名'
    if not date:
        source = '未识别'
    for paragraph in paragraphs:
        # 只把段首短日期标题当作分篇依据；叙述中的日期不自动视为事件日期。
        match = DATE.match(paragraph.strip())
        heading_date = date_in(paragraph) if match and len(paragraph) <= 55 else None
        if heading_date:
            if current:
                result.append((date, source, '\n'.join(current)))
            date, source, current = heading_date, '正文日期标题', []
        current.append(paragraph)
    if current:
        result.append((date, source, '\n'.join(current)))
    return result


def analyze(folder, output_parent):
    import jieba
    jieba.setLogLevel(40)
    stop = STOP.copy()
    stopfile = pathlib.Path(__file__).with_name('stopwords.txt')
    if stopfile.exists():
        stop.update(stopfile.read_text(encoding='utf-8-sig').split())
    userdict = pathlib.Path(__file__).with_name('user_dict.txt')
    if userdict.exists():
        jieba.load_userdict(str(userdict))
    entries, skipped, total = [], [], collections.Counter()
    source_root = folder.parent if folder.is_file() else folder
    paths = [folder] if folder.is_file() else sorted(folder.rglob('*'))
    for path in paths:
        if not path.is_file() or path.name.startswith('~$'):
            continue
        if path.suffix.lower() == '.doc':
            skipped.append({'文件': str(path.relative_to(source_root)), '原因': '旧版 .doc，请用 Word 另存为 .docx'})
            continue
        if path.suffix.lower() != '.docx':
            continue
        name = str(path.relative_to(source_root))
        try:
            paragraphs = extract(path)
            if not paragraphs:
                skipped.append({'文件': name, '原因': '没有可提取正文；图片日记需要 OCR'})
            for date, source, body in split_entries(paragraphs, path.stem):
                words = collections.Counter(w.lower() for w in jieba.lcut(body)
                    if len(w.strip()) > 1 and w.lower() not in stop
                    and re.fullmatch(r'[\u4e00-\u9fffA-Za-z]+', w))
                total.update(words)
                entries.append({'date': date, 'date_source': source, 'file': name,
                                'text': body, 'words': words.most_common(12)})
        except Exception as exc:
            skipped.append({'文件': name, '原因': f'{type(exc).__name__}: {exc}'})
    output_parent.mkdir(parents=True, exist_ok=True)
    out = output_parent / ('日记报告_' + dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    out.mkdir()  # 新建独立报告，不覆盖日记或之前的结果。
    with (out / '词频.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['词语', '次数'])
        writer.writerows(total.most_common())
    with (out / '时间线.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['日期', '日期来源', '原文件', '关键词'])
        for entry in entries:
            # 避免自定义文件名被表格软件作为公式执行。
            safe_name = entry['file']
            if safe_name.startswith(('=', '+', '-', '@')):
                safe_name = "'" + safe_name
            writer.writerow([entry['date'] or '', entry['date_source'], safe_name,
                             '、'.join(w for w, _ in entry['words'])])
    (out / '读取情况.json').write_text(json.dumps({'日记片段数': len(entries), '跳过': skipped}, ensure_ascii=False, indent=2), encoding='utf-8')
    data = json.dumps({'entries': entries, 'top': total.most_common(45), 'skipped': skipped}, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    (out / 'report.html').write_text(PAGE.replace('__DATA__', data), encoding='utf-8')
    return out


PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>我的日记回顾</title>
<style>body{font:16px/1.7 system-ui;margin:0;background:#f6f3ed;color:#273b3a}main{max-width:1000px;margin:auto;padding:35px 22px}h1{font-size:36px;margin-bottom:0}p{color:#60706c}.panel,article{background:white;border-radius:16px;padding:22px;margin:18px 0}input{padding:12px;width:min(85%,500px);font:inherit;border:1px solid #a8bbb3;border-radius:8px}.bar{display:flex;align-items:center;gap:10px;margin:8px 0}.label{width:110px;flex-shrink:0;overflow-wrap:anywhere}.fill{height:14px;background:#3f8d7d;border-radius:6px}.count{font-size:13px}.tag{border:0;background:#e5f0ea;color:#286456;padding:5px 10px;margin:3px;border-radius:12px;cursor:pointer;font:inherit}.meta{color:#647971;font-size:14px}pre{white-space:pre-wrap;font:inherit;overflow-wrap:anywhere}summary{cursor:pointer}#months{display:flex;flex-wrap:wrap;gap:10px}.month{background:#e5f0ea;padding:12px;border-radius:10px}.empty{color:#88652b}</style>
<main><h1>我的日记回顾</h1><p>从词语找到线索，从原文重温经历。</p><div id="stats"></div>
<section class="panel"><b>使用说明</b><p>词频表示提及次数，不代表事情的重要程度。时间线按文件名或正文日期标题归档，并非自动提取的事件发生时间；未识别日期的记录单独列出。只读取正文和表格，不识别图片、批注或页眉页脚。所有内容均在本机处理；报告内包含日记全文。</p></section>
<section class="panel"><h2>常出现的词</h2><p>点击词语，查找相关日记。图表展示全部日记的统计。</p><div id="words"></div></section>
<section class="panel"><h2>每月记录片段</h2><div id="months"></div><p>统计按日期标题切分后的片段数，不等于经历数量。</p></section>
<h2>回忆时间线</h2><input id="query" placeholder="搜索词语、地点、人名或原文…"><span id="match"></span><div id="timeline"></div>
<section class="panel"><h2>读取情况</h2><div id="errors"></div></section></main>
<script>const data=__DATA__;
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n};
document.querySelector('#stats').textContent=`${data.entries.length} 个日记片段 · ${new Set(data.entries.map(e=>e.file)).size} 份已读取文件 · ${data.entries.filter(e=>!e.date).length} 个片段未识别日期`;
for(const [word,count] of data.top){const row=el('div',undefined,'bar');const btn=el('button',word,'tag label');btn.onclick=()=>{document.querySelector('#query').value=word;render();document.querySelector('#query').scrollIntoView({behavior:'smooth'})};const bar=el('div',undefined,'fill');bar.style.width=(count/(data.top[0]?.[1]||1)*55)+'%';row.append(btn,bar,el('span',String(count),'count'));document.querySelector('#words').append(row)}
if(!data.top.length)document.querySelector('#words').textContent='没有可统计的词语。请查看读取情况。';
const months={};for(const e of data.entries){if(e.date){const m=e.date.slice(0,7);months[m]=(months[m]||0)+1}}for(const m of Object.keys(months).sort())document.querySelector('#months').append(el('div',m+' · '+months[m]+' 段','month'));
const sorted=[...data.entries].sort((a,b)=>(a.date||'9999').localeCompare(b.date||'9999'));
function render(){const q=document.querySelector('#query').value.trim().toLowerCase();const list=sorted.filter(e=>(e.text+' '+e.file).toLowerCase().includes(q));const target=document.querySelector('#timeline');target.replaceChildren();document.querySelector('#match').textContent=' '+list.length+' 个片段';for(const e of list){const card=el('article');card.append(el('h3',e.date||'日期待确认'),el('div',e.file+' · 日期来源：'+e.date_source,'meta'));const tags=el('div');for(const [w,n] of e.words)tags.append(el('span',w+' ×'+n,'tag'));card.append(tags,el('p',e.text.slice(0,180)+(e.text.length>180?'…':'')));const details=el('details');details.append(el('summary','展开原文'),el('pre',e.text));card.append(details);target.append(card)}if(!list.length)target.append(el('p','没有匹配的日记。','empty'))}
document.querySelector('#query').oninput=render;render();const errors=document.querySelector('#errors');if(!data.skipped.length)errors.textContent='没有跳过的 Word 文件。';for(const e of data.skipped)errors.append(el('p',e['文件']+'：'+e['原因']));
</script></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', nargs='?', help='单个 .docx 文件，或 Word 日记文件夹')
    parser.add_argument('--output', type=pathlib.Path, default=pathlib.Path(__file__).parent / 'reports')
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    gui = not args.folder
    root = None
    try:
        if gui:
            import tkinter as tk
            from tkinter import filedialog, messagebox
            root = tk.Tk()
            root.withdraw()
            args.folder = filedialog.askdirectory(title='选择 Word 日记所在文件夹')
            if not args.folder:
                return
        folder = pathlib.Path(args.folder).resolve()
        if not folder.is_dir() and not (folder.is_file() and folder.suffix.lower() == '.docx'):
            raise ValueError('请选择存在的 .docx 文件或日记文件夹。')
        out = analyze(folder, args.output)
        print('报告已保存：', out)
        if not args.no_open:
            webbrowser.open((out / 'report.html').resolve().as_uri())
        if gui:
            messagebox.showinfo('完成', '报告已保存到：\n' + str(out))
    except Exception as exc:
        message = str(exc)
        if isinstance(exc, ModuleNotFoundError):
            message += '\n请先运行：py -3.13 -m pip install jieba'
        if gui and root:
            messagebox.showerror('未完成', message)
        else:
            print(message, file=sys.stderr)
        sys.exit(1)
    finally:
        if root:
            root.destroy()


if __name__ == '__main__':
    main()
