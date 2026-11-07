"""Экспорт: книга (md / html / pdf) и полный архив данных пользователя (zip)."""
import html
import io
import json
import zipfile
from pathlib import Path


def book_title(settings):
    name = settings.get("preferred_name")
    return f"История жизни: {name}" if name else "История жизни"


def book_markdown(settings, chapters):
    parts = [f"# {book_title(settings)}", ""]
    for ch in chapters:
        parts += [f"## {ch['title']}", "", ch["body"].strip(), ""]
    return "\n".join(parts).strip() + "\n"


_CSS = """
@page { size: A5; margin: 18mm 16mm; }
body { font-family: 'Georgia', 'Times New Roman', serif; font-size: 12pt; line-height: 1.55; color: #222; }
h1 { text-align: center; font-size: 26pt; margin: 40mm 0 10mm; }
h2 { font-size: 16pt; margin-top: 0; page-break-before: always; }
p { margin: 0 0 0.8em; text-align: justify; }
.cover { page-break-after: always; }
"""


def book_html(settings, chapters):
    esc = html.escape
    out = [f"<!doctype html><html lang='ru'><head><meta charset='utf-8'><title>{esc(book_title(settings))}</title>",
           f"<style>{_CSS}</style></head><body><div class='cover'><h1>{esc(book_title(settings))}</h1></div>"]
    for ch in chapters:
        out.append(f"<h2>{esc(ch['title'])}</h2>")
        for para in [p for p in ch["body"].split("\n\n") if p.strip()]:
            out.append(f"<p>{esc(para.strip()).replace(chr(10), '<br>')}</p>")
    out.append("</body></html>")
    return "".join(out)


def book_pdf(settings, chapters):
    try:
        from weasyprint import HTML  # опциональная зависимость, в Docker-образе установлена
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("PDF недоступен: установите weasyprint (см. docs/05-deployment.md)") from e
    return HTML(string=book_html(settings, chapters)).write_pdf()


def data_zip(profile, recordings, events, chapters, audio_root: Path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("profile.json", json.dumps(profile, ensure_ascii=False, indent=2))
        z.writestr("transcripts.json", json.dumps([{k: v for k, v in r.items() if k != "audio_path"} for r in recordings], ensure_ascii=False, indent=2))
        z.writestr("events.json", json.dumps(events, ensure_ascii=False, indent=2))
        z.writestr("chapters.json", json.dumps(chapters, ensure_ascii=False, indent=2))
        for rec in recordings:
            p = rec.get("audio_path")
            if p and Path(p).is_file() and Path(p).resolve().is_relative_to(audio_root.resolve()):
                z.write(p, f"audio/{Path(p).name}")
    return buf.getvalue()
