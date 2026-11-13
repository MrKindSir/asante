"""Portable story documents and disk-backed ZIP exports, without external URL fetches."""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import tempfile
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, BinaryIO
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import reportlab
from fastapi import HTTPException
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, KeepTogether
from reportlab.graphics.shapes import Drawing, Rect, String

from .storage import media_bucket, storage_client


def plain(value: Any) -> str:
    text = re.sub(r"</(?:p|div|h[1-6]|li)>|<br\s*/?>", "\n", str(value or ""), flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def report_sections(document: dict[str, Any]) -> list[tuple[str, list[str]]]:
    sections = [("Summary", [plain(document.get("summary"))])]
    for section in document.get("sections") or []:
        sections.append((plain(section.get("title")), [
            plain(section.get("body")),
            *(f"- {plain(item)}" for item in section.get("bullets") or []),
        ]))
    for chart in document.get("charts") or []:
        sections.append((plain(chart.get("title")), [
            f"{plain(item.get('label'))}: {item.get('value')} {plain(chart.get('unit'))}".strip()
            for item in chart.get("series") or []
        ]))
    for table in document.get("tables") or []:
        sections.append((plain(table.get("title")), [
            " | ".join(plain(item) for item in table.get("columns") or []),
            *(" | ".join(plain(cell) for cell in row) for row in table.get("rows") or []),
        ]))
    sources = []
    for index, source in enumerate(document.get("sources") or [], 1):
        sources.extend([f"[{index}] {plain(source.get('title'))}", str(source.get("url") or ""), plain(source.get("note"))])
    if sources:
        sections.append(("Sources - candidates for human review", sources))
    images = document.get("images") or []
    if images:
        sections.append(("Related image references", [
            f"{plain(image.get('caption'))} | {plain(image.get('credit'))}\n{image.get('url') or ''}"
            for image in images
        ]))
    sections.append(("Human review", [plain(document.get("humanGate")) or "A human reviewer must approve publication."]))
    return sections


def render_report_pdf(document: dict[str, Any]) -> bytes:
    """Render the field-report document with matching section, chart and table structure."""
    font_dir = Path(reportlab.__file__).parent / "fonts"
    # Register once; ReportLab's bundled fonts keep local/container exports identical.
    if "AsanteReport" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("AsanteReport", str(font_dir / "Vera.ttf")))
        pdfmetrics.registerFont(TTFont("AsanteReportBold", str(font_dir / "VeraBd.ttf")))
    styles = getSampleStyleSheet()
    body = ParagraphStyle("AsanteBody", fontName="AsanteReport", fontSize=10, leading=15, spaceAfter=8, alignment=TA_LEFT, splitLongWords=True)
    heading = ParagraphStyle("AsanteHeading", parent=body, fontName="AsanteReportBold", fontSize=13, leading=18, spaceBefore=16, spaceAfter=8, keepWithNext=True, textColor=colors.HexColor("#121816"))
    title = ParagraphStyle("AsanteTitle", parent=styles["Title"], fontName="AsanteReportBold", fontSize=23, leading=29, alignment=TA_LEFT, spaceAfter=12, textColor=colors.HexColor("#121816"))
    accent = colors.HexColor("#f28c28")

    def paragraph(value: Any, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(html.escape(plain(value)).replace("\n", "<br/>"), style)

    flow = [paragraph("ASANTE / CONTRIBUTOR FIELD REPORT", heading), paragraph(document.get("title") or "Story report", title)]
    if document.get("subtitle"):
        flow.append(paragraph(document["subtitle"]))
    if document.get("landmark"):
        flow.append(paragraph("PLACE  /  " + str(document["landmark"])))
    flow.extend([Spacer(1, 6), paragraph("01 / Executive summary", heading), paragraph(document.get("summary") or "")])
    for index, section in enumerate(document.get("sections") or [], 2):
        flow.append(paragraph(f"{index:02d} / {section.get('title') or 'Story notes'}", heading))
        if section.get("body"):
            flow.append(paragraph(section["body"]))
        for bullet in section.get("bullets") or []:
            flow.append(paragraph("•  " + str(bullet)))
    for chart in document.get("charts") or []:
        series = chart.get("series") or []
        if not series:
            continue
        flow.append(paragraph(chart.get("title") or "Chart", heading))
        max_value = max((abs(float(item.get("value") or 0)) for item in series), default=1) or 1
        chart_height = 34 + len(series) * 24
        drawing = Drawing(511, chart_height)
        for row, item in enumerate(series):
            y = chart_height - 24 - row * 24
            label = plain(item.get("label"))[:60]
            value = float(item.get("value") or 0)
            drawing.add(String(0, y + 4, label, fontName="AsanteReport", fontSize=8, fillColor=colors.HexColor("#121816")))
            drawing.add(Rect(190, y, 250 * abs(value) / max_value, 12, fillColor=accent, strokeColor=None))
            suffix = f" {chart.get('unit')}" if chart.get("unit") else ""
            drawing.add(String(448, y + 3, f"{value:g}{suffix}", fontName="AsanteReport", fontSize=8, fillColor=colors.HexColor("#121816")))
        flow.append(drawing)
    for table in document.get("tables") or []:
        columns = [plain(item) for item in table.get("columns") or []]
        if not columns:
            continue
        flow.append(paragraph(table.get("title") or "Table", heading))
        data = [[paragraph(item, body) for item in columns]]
        data.extend([[paragraph(item, body) for item in row[:len(columns)]] for row in table.get("rows") or []])
        block = Table(data, colWidths=[511 / len(columns)] * len(columns), repeatRows=1, hAlign="LEFT")
        block.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#121816")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("LINEBELOW", (0, 0), (-1, 0), 2, accent),
            ("GRID", (0, 1), (-1, -1), 0.4, colors.HexColor("#c8d2cc")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        flow.append(block)
    if document.get("images"):
        flow.append(paragraph("Related visual references", heading))
        for image in document["images"]:
            caption = plain(image.get("caption")) or "Related image"
            credit = plain(image.get("credit")) or "Credit unavailable"
            url = str(image.get("url") or "")
            flow.append(KeepTogether([paragraph(caption, body), paragraph("Credit: " + credit), paragraph(url)]))
    if document.get("sources"):
        flow.append(paragraph("References / candidate sources", heading))
        for index, source in enumerate(document["sources"], 1):
            flow.append(KeepTogether([paragraph(f"[{index}] {source.get('title') or source.get('url')}", body), paragraph(source.get("url") or ""), paragraph(source.get("excerpt") or ""), paragraph(" · ".join(value for value in [source.get("publisher") or "", source.get("status") or "candidate", source.get("retrievedAt") or ""] if value))]))
    flow.extend([paragraph("HUMAN REVIEW GATE", heading), paragraph(document.get("humanGate") or "A human reviewer must approve publication."), paragraph("Asante workers do not publish stories.")])
    buffer = BytesIO()

    def footer(canvas, doc):
        canvas.setFont("AsanteReport", 8)
        canvas.setFillColor(colors.HexColor("#5c6661"))
        canvas.drawString(42, 25, "Asante | Candidate evidence requires human review")
        canvas.drawRightString(553, 25, str(doc.page))

    SimpleDocTemplate(buffer, pagesize=(595, 842), leftMargin=42, rightMargin=42, topMargin=36, bottomMargin=48, title=plain(document.get("title"))).build(flow, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def default_document(packet: dict[str, Any]) -> dict[str, Any]:
    plan = packet.get("plan") or {}
    research = packet.get("research") or {}
    report = research.get("report") or {}
    return {
        "title": packet.get("title") or "Untitled story",
        "landmark": packet.get("place") or "",
        "summary": report.get("summary") or packet.get("claim") or ("Story brief and available planning material." if plan else "Story brief. A story plan has not been prepared yet."),
        "sections": [
            {"title": label, "bullets": plan.get(key) or []}
            for key, label in [("outline", "Outline"), ("questions", "Open questions"), ("checklist", "Checklist"), ("unknowns", "Unknowns")]
        ] + [
            {"title": "Research findings", "bullets": [f"{finding.get('text') or ''} ({', '.join(finding.get('sourceUrls') or [])})" for finding in report.get("findings") or []]},
            {"title": "Questions for human review", "bullets": report.get("openQuestions") or []},
        ],
        "sources": [{"title": source.get("title"), "url": source.get("url"), "note": source.get("excerpt")} for source in research.get("sources") or []],
        "images": research.get("images") or [],
        "humanGate": plan.get("human_gate"),
    }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _csv_cell(value: Any) -> str:
    text = str(value or "")
    # Research text is untrusted; keep spreadsheet programs from evaluating it.
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text


def _attach_recording(archive: ZipFile, media: dict[str, Any]) -> str:
    extensions = {"audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/ogg": ".ogg", "video/mp4": ".mp4", "video/webm": ".webm"}
    name = "media/original" + extensions.get(media["type"], ".bin")
    response = None
    try:
        response = storage_client().get_object(media_bucket(), media["objectKey"])
        digest = hashlib.sha256()
        size = 0
        with archive.open(name, "w", force_zip64=True) as target:
            for chunk in response.stream(64 * 1024):
                size += len(chunk)
                if size > media["size"]:
                    raise ValueError("Recording exceeds verified size")
                target.write(chunk)
                digest.update(chunk)
        if size != media["size"] or digest.hexdigest() != media["checksum"]:
            raise ValueError("Recording does not match verified checksum")
    except Exception as error:
        raise HTTPException(503, "The original recording could not be included. Please retry the ZIP download.") from error
    finally:
        if response is not None:
            response.close()
            response.release_conn()
    return name


def build_packet_archive(packet: dict[str, Any], document: dict[str, Any] | None = None, media: dict[str, Any] | None = None) -> BinaryIO:
    """Build completely before delivery so storage errors cannot masquerade as success."""
    report = document or (packet.get("plan") or {}).get("document") or default_document(packet)
    sections = report_sections(report)
    text = "\n\n".join(["ASANTE FIELD REPORT", plain(report.get("title")), plain(report.get("landmark")), *(label + "\n" + "\n".join(lines) for label, lines in sections)]) + "\n"
    report_html = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Asante field report</title><style>body{font:16px/1.6 system-ui,sans-serif;max-width:850px;margin:40px auto;padding:0 24px;color:#253d34}h1{line-height:1.2}pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere}h2{margin-top:32px}</style><body>'
    report_html += "<h1>" + html.escape(plain(report.get("title"))) + "</h1><p>" + html.escape(plain(report.get("landmark"))) + "</p>"
    report_html += "".join("<h2>" + html.escape(label) + "</h2><pre>" + html.escape("\n\n".join(line for line in lines if line)) + "</pre>" for label, lines in sections if any(lines)) + "</body></html>\n"
    brief = "\n".join(f"{label}: {plain(packet.get(key))}" for key, label in [
        ("title", "Story"), ("attribution", "Contributor credit"), ("place", "Place"), ("language", "Language"),
        ("format", "Media format"), ("audience", "Audience"), ("claim", "Claim / question"), ("source", "Supplied source"),
        ("suggestion", "Plan decision"), ("extraNotes", "Contributor notes"), ("version", "Project version"), ("exportedAt", "Exported at (UTC)"),
    ]) + "\n"
    files: dict[str, str | bytes] = {
        "story-brief.txt": brief,
        "field-report.pdf": render_report_pdf(report),
        "field-report.html": report_html,
        "field-report.txt": text,
        "project.json": _json(packet),
    }
    missing = []
    if not packet.get("plan"):
        missing.append("Story plan: not prepared; the field report contains the available brief and research.")
    if packet.get("transcript"):
        files["transcript.txt"] = str(packet["transcript"]) + "\n"
    else:
        missing.append("Transcript: not added yet.")
    research = packet.get("research")
    if research:
        files["research/research.json"] = _json(research)
        lines = ["ASANTE RESEARCH - CANDIDATE SOURCES", "Sources are candidates for human comparison, not verified proof.",
                 f"Query: {research.get('searchQuery') or ''}", f"Focus: {research.get('focus') or ''}", str(research.get("summary") or ""),
                 *(str(note) for note in research.get("notes") or [])]
        report = research.get("report") or {}
        for finding in report.get("findings") or []:
            lines.extend(["", str(finding.get("text") or ""), *(str(url) for url in finding.get("sourceUrls") or [])])
        if report.get("openQuestions"):
            lines.extend(["", "Questions for human review", *(str(question) for question in report["openQuestions"])])
        columns = ["title", "url", "excerpt", "collector", "status", "platform", "publisher", "retrievedAt", "contentHash"]
        csv_buffer = StringIO(newline="")
        writer = csv.writer(csv_buffer)
        writer.writerow(columns)
        for index, source in enumerate(research.get("sources") or [], 1):
            writer.writerow([_csv_cell(source.get(key)) for key in columns])
            lines.extend(["", f"[{index}] {source.get('title') or ''}", str(source.get("url") or ""), str(source.get("excerpt") or ""),
                          f"Publisher: {source.get('publisher') or ''} | Retrieved: {source.get('retrievedAt') or ''} | Status: {source.get('status') or 'candidate'}"])
        for image in research.get("images") or []:
            lines.extend(["", f"Image reference: {image.get('caption') or ''}", str(image.get("url") or ""), f"Credit: {image.get('credit') or ''}"])
        files["research/sources.csv"] = "\ufeff" + csv_buffer.getvalue()
        files["research/research-notes.txt"] = "\n".join(lines) + "\n"
    else:
        missing.append("Research: not run yet.")
    if packet.get("researchHistory"):
        files["research/worker-history.json"] = _json(packet["researchHistory"])
        lines = ["ASANTE RESEARCH WORKER HISTORY"]
        for run in packet["researchHistory"]:
            lines.extend(["", f"Run: {run['runId']} | {run['status']} | {run['createdAt']}", f"Trace: {run['traceId']}"])
            for step in ((run.get("result") or {}).get("team") or {}).get("steps") or []:
                lines.extend([f"{step['title']}: {step['status']}", f"Started: {step.get('startedAt') or '-'} | Finished: {step.get('finishedAt') or '-'}",
                              str(step.get("summary") or step.get("safeError") or ""), *(str(item) for item in step.get("highlights") or [])])
        files["research/worker-history.txt"] = "\n".join(lines) + "\n"
    verification = packet.get("verification")
    if verification:
        files["verification.json"] = _json(verification)
        lines = ["ASANTE VERIFICATION", str(verification.get("summary") or "")]
        for finding in verification.get("findings") or []:
            lines.extend([f"{finding.get('severity') or ''}: {finding.get('message') or ''}", str(finding.get("rationale") or ""),
                          *(str(reference) for reference in finding.get("references") or [])])
        files["verification.txt"] = "\n".join(lines) + "\n"
    else:
        missing.append("Verification: no findings available yet.")

    temporary = tempfile.TemporaryFile(prefix="asante-packet-")
    try:
        with ZipFile(temporary, "w", allowZip64=True) as archive:
            for name, data in files.items():
                archive.writestr(name, data, compress_type=ZIP_DEFLATED)
            if media:
                # Recordings are already compressed; store without another expensive compression pass.
                archive.compression = ZIP_STORED
                name = _attach_recording(archive, media)
                files[name] = b""
                archive.writestr("media/recording.json", _json({key: value for key, value in media.items() if key != "objectKey"}))
                files["media/recording.json"] = ""
            else:
                missing.append("Original recording: no verified recording attached.")
            guide = "ASANTE STORY DOWNLOAD PACK\n\n" + brief + "\nCONTENTS\n" + "\n".join(f"- {name}" for name in files)
            guide += "\n\nOpen field-report.pdf to read or print. HTML and UTF-8 text copies preserve the full text.\nproject.json preserves structured project data. research/sources.csv opens in a spreadsheet.\n"
            guide += "Research pages and related images are referenced by URL, with available credits; third-party files are not copied into this ZIP.\nResearch candidates and worker findings require human review. This export does not approve publication.\n"
            guide += "\nNOT AVAILABLE\n" + ("\n".join(f"- {note}" for note in missing) or "All supported sections are present.") + "\n"
            archive.writestr("README.txt", guide, compress_type=ZIP_DEFLATED)
        temporary.seek(0)
        return temporary
    except BaseException:
        temporary.close()
        raise
