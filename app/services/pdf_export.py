import io
from datetime import datetime
from typing import Any, List, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def generate_k3_pdf_report(
    summary_data: dict,
    violations: List[Any],
    workers: List[Any],
    date_str: str,
    sections: List[str],
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "K3Title",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "K3Subtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#475569"),
        spaceAfter=14,
    )
    heading_style = ParagraphStyle(
        "K3Heading",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#DE643B"),
        spaceBefore=12,
        spaceAfter=6,
    )
    cell_style = ParagraphStyle(
        "K3Cell",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
    )
    cell_header = ParagraphStyle(
        "K3CellHeader",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        fontName="Helvetica-Bold",
        textColor=colors.white,
    )

    elements = []

    # Header
    elements.append(Paragraph("PT. PARAMA DATA UNIT (PDU MIGAS)", title_style))
    elements.append(Paragraph(f"Laporan Pemantauan Kepatuhan APD K3 - Tanggal: {date_str}", subtitle_style))
    elements.append(Spacer(1, 8))

    # Section 1: Summary
    if "summary" in sections:
        elements.append(Paragraph("1. Ringkasan Kepatuhan K3", heading_style))
        summary_rows = [
            [Paragraph("Indikator", cell_header), Paragraph("Nilai", cell_header)],
            [Paragraph("Total Sesi Deteksi", cell_style), Paragraph(str(summary_data.get("total_sessions", 0)), cell_style)],
            [Paragraph("Total Pekerja Terpantau", cell_style), Paragraph(str(summary_data.get("total_workers", 0)), cell_style)],
            [Paragraph("Tingkat Kepatuhan Keseluruhan", cell_style), Paragraph(f"{summary_data.get('compliance_rate', 0.0)}%", cell_style)],
        ]
        violations_by_apd = summary_data.get("violations_by_apd", [])
        for v in violations_by_apd:
            apd_name = v.get("apd", "").capitalize()
            v_cnt = v.get("violation_count", 0)
            c_pct = v.get("compliance_percentage", 0.0)
            summary_rows.append([
                Paragraph(f"Pelanggaran {apd_name}", cell_style),
                Paragraph(f"{v_cnt} pelanggaran ({c_pct}% patuh)", cell_style),
            ])

        t_summary = Table(summary_rows, colWidths=[200, 320])
        t_summary.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(t_summary)
        elements.append(Spacer(1, 12))

    # Section 2: Violations
    if "violations" in sections:
        elements.append(Paragraph("2. Daftar Pelanggaran APD", heading_style))
        v_rows = [
            [
                Paragraph("Waktu", cell_header),
                Paragraph("Pekerja", cell_header),
                Paragraph("Lokasi / Kamera", cell_header),
                Paragraph("APD Kurang", cell_header),
                Paragraph("Status", cell_header),
                Paragraph("Penanganan", cell_header),
            ]
        ]
        if not violations:
            v_rows.append([
                Paragraph("Nihil", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("Tidak ada pelanggaran tercatat", cell_style),
            ])
        else:
            for v in violations:
                t_str = v.detected_at.strftime("%H:%M:%S") if v.detected_at else "-"
                worker_label = f"{v.worker_id} ({v.worker_role or 'Pekerja'})"
                loc_cam = f"{v.location or '-'} / {v.camera_code or '-'}"
                missing_str = v.missing_apd if isinstance(v.missing_apd, str) else ", ".join(v.missing_apd)
                status_str = "Ditangani" if v.status == "handled" else "Belum Ditangani"
                handled_info = f"{v.handled_by or '-'}: {v.handling_note or '-'}" if v.status == "handled" else "-"

                v_rows.append([
                    Paragraph(t_str, cell_style),
                    Paragraph(worker_label, cell_style),
                    Paragraph(loc_cam, cell_style),
                    Paragraph(missing_str, cell_style),
                    Paragraph(status_str, cell_style),
                    Paragraph(handled_info, cell_style),
                ])

        t_viol = Table(v_rows, colWidths=[55, 95, 110, 80, 70, 110])
        t_viol.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DE643B")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(t_viol)
        elements.append(Spacer(1, 12))

    # Section 3: Personnel
    if "personnel" in sections:
        elements.append(Paragraph("3. Catatan Personil Terdeteksi", heading_style))
        w_rows = [
            [
                Paragraph("ID", cell_header),
                Paragraph("Kamera", cell_header),
                Paragraph("Lokasi", cell_header),
                Paragraph("Helm", cell_header),
                Paragraph("Kacamata", cell_header),
                Paragraph("Glove", cell_header),
                Paragraph("Sepatu", cell_header),
                Paragraph("Status", cell_header),
            ]
        ]
        if not workers:
            w_rows.append([
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("Tidak ada personil tercatat", cell_style),
            ])
        else:
            for w in workers[:50]:  # Batasi 50 personil pada tabel ringkas
                w_id = f"W-{w.track_id}" if w.track_id else f"#{w.id}"
                cam = w.camera_code or "-"
                loc = w.location or "-"
                helm = "Ya" if w.helm_worn else "Tidak"
                kac = "Ya" if w.kacamata_worn else "Tidak"
                glv = "Ya" if w.glove_worn else "Tidak"
                sep = "Ya" if w.sepatu_worn else "Tidak"
                status_w = "Patuh" if w.is_compliant else "Pelanggaran"

                w_rows.append([
                    Paragraph(w_id, cell_style),
                    Paragraph(cam, cell_style),
                    Paragraph(loc, cell_style),
                    Paragraph(helm, cell_style),
                    Paragraph(kac, cell_style),
                    Paragraph(glv, cell_style),
                    Paragraph(sep, cell_style),
                    Paragraph(status_w, cell_style),
                ])

        t_work = Table(w_rows, colWidths=[55, 60, 95, 50, 60, 50, 50, 100])
        t_work.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(t_work)

    doc.build(elements)
    return buffer.getvalue()
