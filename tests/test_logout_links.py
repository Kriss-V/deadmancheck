from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "app" / "templates"


def test_no_template_logs_out_with_a_get_link():
    # /logout is POST-only; a plain link sends GET and 404s
    offenders = [str(p.relative_to(TEMPLATES)) for p in TEMPLATES.rglob("*.html") if 'href="/logout"' in p.read_text(encoding="utf-8")]
    assert offenders == []
