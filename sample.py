import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

def _summary_df_to_html(df: pd.DataFrame, title: str = "Overall Summary") -> str:
    """Render summary_df inline with conditional coloring."""
    if df is None or df.empty:
        return f"<h3>{title}</h3><p><i>No rows.</i></p>"

    cols_norm = {c: c.strip().lower() for c in df.columns}
    passed_col = next((c for c, n in cols_norm.items() if n == "passed"), None)
    failed_col = next((c for c, n in cols_norm.items() if n == "failed"), None)

    def fmt_cell(val, col):
        if col == passed_col:
            return f'<span style="color:#1a7f37;font-weight:700;">{val}</span>'
        if col == failed_col:
            return f'<span style="color:#d1242f;font-weight:700;">{val}</span>'
        return str(val)

    header_cells = "".join(
        f'<th style="border:1px solid #ddd;padding:6px 8px;background:#f2f2f2;text-align:left;">{c}</th>'
        for c in df.columns
    )

    body_rows = []
    for _, row in df.iterrows():
        row_failed_val = 0
        if failed_col is not None:
            try:
                row_failed_val = int(row[failed_col]) if pd.notna(row[failed_col]) else 0
            except Exception:
                row_failed_val = 0

        tr_style = 'background:#fff5f5;' if row_failed_val > 0 else ''
        tds = []
        for c in df.columns:
            v = "" if pd.isna(row[c]) else row[c]
            tds.append(
                f'<td style="border:1px solid #ddd;padding:6px 8px;text-align:left;">{fmt_cell(v, c)}</td>'
            )
        body_rows.append(f'<tr style="{tr_style}">' + "".join(tds) + "</tr>")

    return f"""
    <h3>{title}</h3>
    <table style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px;">
      <thead><tr>{header_cells}</tr></thead>
      <tbody>{''.join(body_rows)}</tbody>
    </table>
    """


def send_summary_email(
    recipients,
    subject,
    summary_df: pd.DataFrame,
    sender="saisrikar.ravipati@cvshealth.com",
    smtp_host="smtppaz.corp.cvscaremark.com",
    smtp_port=25,
    use_starttls=True
):
    """Send ONLY the summary_df inline — no identifiers, no attachments."""
    
    summary_html = _summary_df_to_html(summary_df, title="Overall Summary")

    html_body = f"""
    <html>
      <body style="font-family:Arial,sans-serif;">
        <p>Hello Team,</p>

        <p>Below is the Overall Summary for this run:</p>
        {summary_html}

        <p>Thanks!</p>
      </body>
    </html>
    """

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if use_starttls:
                try:
                    server.starttls()
                except Exception:
                    pass
            server.sendmail(sender, recipients, msg.as_string())
        print("Email sent successfully!")
    except Exception as e:
        print(f"Error sending email: {e}")
