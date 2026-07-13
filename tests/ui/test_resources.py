from pathlib import Path
from xml.etree import ElementTree

from PySide6.QtGui import QPixmap


def test_team_logo_is_self_contained_svg_with_approved_identity(qapp) -> None:
    logo_path = Path(__file__).parents[2] / "assets" / "brand" / "team-logo.svg"
    root = ElementTree.parse(logo_path).getroot()
    source = logo_path.read_text(encoding="utf-8")

    assert root.tag.endswith("svg")
    assert "湖大智竹实践团队" in source
    assert "#2FA47D" in source
    assert "#294D3C" in source
    assert not any(element.tag.endswith("image") for element in root.iter())
    assert "href=" not in source
    assert QPixmap(str(logo_path)).isNull() is False
